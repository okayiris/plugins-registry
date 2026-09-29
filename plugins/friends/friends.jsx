// The owner's window: the feed of friends and followed walls, their own wall with likes and comments,
// and friends: requests to answer, someone to add, who follows whom. Everything goes through the
// plugin's own command with /commands/run; the feed is fetched from the other houses when it shows.

const run = async (args) => {
  try {
    const r = await fetch("/commands/run", { method: "POST", body: JSON.stringify({ cmd: "friends", args }) });
    const d = await r.json();
    return d || { ok: false, tekst: "" };
  } catch (e) {
    return { ok: false, tekst: String((e && e.message) || e) };
  }
};

const json = async (args) => {
  const d = await run(args);
  if (!d.ok) return null;
  try {
    return JSON.parse(d.tekst);
  } catch (e) {
    return null;
  }
};

// Words go to the command as one quoted argument; a double quote inside would end it early.
const quoted = (s) => `"${String(s).replace(/"/g, "'").replace(/\s+/g, " ").trim()}"`;

const count = (n, one, many) => (n === 1 ? one : many).replace("{n}", n);

const since = (at) => {
  const s = Math.max(0, Date.now() / 1000 - at);
  const lang = document.documentElement.lang || undefined;
  try {
    const rtf = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
    if (s < 60) return rtf.format(0, "second");
    if (s < 3600) return rtf.format(-Math.floor(s / 60), "minute");
    if (s < 86400) return rtf.format(-Math.floor(s / 3600), "hour");
    if (s < 7 * 86400) return rtf.format(-Math.floor(s / 86400), "day");
    return new Date(at * 1000).toLocaleDateString(lang, { day: "numeric", month: "short" });
  } catch (e) {
    return new Date(at * 1000).toLocaleDateString();
  }
};

const Photo = ({ house, id }) => {
  const [src, setSrc] = useState("");
  useEffect(() => {
    let live = true;
    void json(`photo ${house} ${id} --json`).then((d) => {
      if (live && d && d.data) setSrc(`data:${d.type};base64,${d.data}`);
    });
    return () => { live = false; };
  }, [house, id]);
  return src ? (
    <img src={src} alt="" loading="lazy"
         style={{ width: "100%", maxHeight: "28rem", objectFit: "cover", display: "block", borderRadius: ".7rem", marginTop: ".5rem" }} />
  ) : (
    <div style={{ width: "100%", aspectRatio: "4 / 3", maxHeight: "28rem", borderRadius: ".7rem", marginTop: ".5rem",
                  background: "var(--glass)", border: "1px solid var(--edge)" }} />
  );
};

const field = { width: "100%", boxSizing: "border-box", background: "var(--glass)", color: "var(--fg)", minWidth: 0,
                border: "1px solid var(--edge)", borderRadius: ".6rem", padding: ".5rem .65rem", font: "inherit" };
const small = { color: "var(--dim)", fontSize: ".82rem" };
const box = { borderTop: "1px solid var(--edge)", padding: ".75rem 0", minWidth: 0 };

const Thread = ({ items }) => (items && items.length ? (
  <div style={{ marginTop: ".45rem", display: "flex", flexDirection: "column", gap: ".25rem" }}>
    {items.map((c, i) => (
      <div key={i} style={{ fontSize: ".86rem", overflowWrap: "anywhere" }}>
        <b style={{ fontWeight: 600 }}>{c.name || c.house}</b> <span style={{ color: "var(--dim)" }}>{c.text}</span>
      </div>
    ))}
  </div>
) : null);

const Post = ({ p, own, reload }) => {
  const [open, setOpen] = useState(false);
  const [words, setWords] = useState("");
  const [liked, setLiked] = useState(!!p.liked);
  const [likes, setLikes] = useState(p.likes || 0);
  const [thread, setThread] = useState(p.thread || []);
  const [problem, setProblem] = useState("");
  const ref = `${own ? "me" : p.house}/${p.id}`;

  const like = async () => {
    const d = await run(`${liked ? "unlike" : "like"} ${ref}`);
    if (d.ok) {
      setLikes(likes + (liked ? -1 : 1));
      setLiked(!liked);
    } else setProblem(d.tekst);
  };
  const send = async () => {
    if (!words.trim()) return;
    const d = await run(`comment ${ref} ${quoted(words)}`);
    if (d.ok) {
      setThread([...thread, { name: text("you", "You"), text: words.trim() }]);
      setWords("");
      setOpen(false);
      if (own) void reload();
    } else setProblem(d.tekst);
  };
  const remove = async () => {
    const d = await run(`delete ${p.id}`);
    if (d.ok) void reload(); else setProblem(d.tekst);
  };

  return (
    <div style={box}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: ".6rem", alignItems: "baseline", flexWrap: "wrap" }}>
        <b style={{ fontWeight: 600, overflowWrap: "anywhere" }}>{own ? text("you", "You") : p.name || p.house}</b>
        <span style={small}>
          {since(p.at)} · {p.audience === "public" ? text("public", "Everyone") : text("friendsOnly", "Friends")}
        </span>
      </div>
      {p.text ? <div style={{ whiteSpace: "pre-line", marginTop: ".3rem", overflowWrap: "anywhere" }}>{p.text}</div> : null}
      {p.photo ? <Photo house={own ? "me" : p.house} id={p.id} /> : null}
      {own && p.liked_by && p.liked_by.length ? (
        <div style={{ ...small, marginTop: ".4rem" }}>{text("likedBy", "Liked by {names}").replace("{names}", p.liked_by.join(", "))}</div>
      ) : null}
      <Thread items={thread} />
      <Buttons>
        {p.friend && !own ? (
          <Button primary={liked} onClick={like}>{liked ? text("liked", "Liked") : text("like", "Like")}{likes ? ` · ${likes}` : ""}</Button>
        ) : likes ? <span style={small}>{count(likes, text("likeOne", "{n} like"), text("likes", "{n} likes"))}</span> : null}
        {own || p.friend ? (
          <Button onClick={() => setOpen(!open)}>{text("comment", "Comment")}{p.comments ? ` · ${p.comments}` : ""}</Button>
        ) : null}
        {own ? <Button onClick={remove}>{text("delete", "Delete")}</Button> : null}
      </Buttons>
      {open ? (
        <div style={{ display: "flex", gap: ".4rem", alignItems: "center", flexWrap: "wrap" }}>
          <input style={{ ...field, flex: "1 1 12rem" }} value={words} placeholder={text("commentHint", "Write a comment")}
                 onInput={(e) => setWords(e.currentTarget.value)} onKeyDown={(e) => { if (e.key === "Enter") void send(); }} />
          <Buttons><Button primary onClick={send}>{text("send", "Send")}</Button></Buttons>
        </div>
      ) : null}
      {problem ? <Text dim>{problem}</Text> : null}
    </div>
  );
};

export default () => {
  const [tab, setTab] = useState("feed");
  const [data, setData] = useState(null);
  const [feed, setFeed] = useState(null);
  const [missed, setMissed] = useState([]);
  const [draft, setDraft] = useState("");
  const [audience, setAudience] = useState("");
  const [who, setWho] = useState("");
  const [problem, setProblem] = useState("");

  const load = async () => {
    const d = await json("data --json");
    if (d) {
      setData(d);
      if (!feed) setFeed(d.feed);
    } else setProblem(text("unavailable", "Your wall cannot be read right now."));
  };
  const fetchFeed = async () => {
    const f = await json("feed --json");
    if (f) {
      setFeed(f.feed || []);
      setMissed(f.missed || []);
    }
  };

  useEffect(() => {
    void load().then(() => fetchFeed());
  }, []);

  const post = async () => {
    if (!draft.trim()) return;
    const d = await run(`post ${quoted(draft)} ${audience || (data && data.me.audience) || "friends"}`);
    if (d.ok) {
      setDraft("");
      setProblem("");
      setTab("wall");
      void load();
    } else setProblem(d.tekst);
  };
  const act = async (args) => {
    const d = await run(args);
    setProblem(d.ok ? "" : d.tekst);
    void load();
    if (d.ok) void fetchFeed();
  };

  if (!data) {
    return (
      <Card label={text("label", "Friends")} title={text("title", "Your wall")}>
        <Text dim>{problem || text("loading", "Loading your wall...")}</Text>
      </Card>
    );
  }

  const me = data.me || {};
  const chosen = audience || me.audience || "friends";
  const asked = data.asked || [];
  const fresh = (data.news || []).filter((n) => !n.seen && n.kind !== "request");

  const composer = (
    <div style={{ display: "flex", flexDirection: "column", gap: ".45rem", marginBottom: ".4rem" }}>
      <textarea style={{ ...field, minHeight: "4.2rem", resize: "vertical" }} value={draft}
                placeholder={text("postHint", "What do you want to share?")} onInput={(e) => setDraft(e.currentTarget.value)} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".5rem", flexWrap: "wrap" }}>
        <Buttons>
          <span style={small}>{text("for", "For")}</span>
          <Button primary={chosen === "friends"} onClick={() => setAudience("friends")}>{text("friendsOnly", "Friends")}</Button>
          <Button primary={chosen === "public"} onClick={() => setAudience("public")}>{text("public", "Everyone")}</Button>
        </Buttons>
        <Buttons><Button primary onClick={post}>{text("post", "Post")}</Button></Buttons>
      </div>
      <span style={small}>{text("photoHint", "A photo? Send it to Iris and say: put this on my wall.")}</span>
    </div>
  );

  return (
    <Card label={text("label", "Friends")} title={me.name || text("title", "Your wall")}>
      <Buttons>
        <Button primary={tab === "feed"} onClick={() => setTab("feed")}>{text("feed", "Feed")}</Button>
        <Button primary={tab === "wall"} onClick={() => setTab("wall")}>{text("wall", "My wall")}</Button>
        <Button primary={tab === "friends"} onClick={() => setTab("friends")}>
          {text("friends", "Friends")}{asked.length ? ` · ${asked.length}` : ""}
        </Button>
      </Buttons>
      {problem ? <Text dim>{problem}</Text> : null}

      {tab === "feed" ? (
        <div>
          {composer}
          {fresh.length ? (
            <div style={{ ...box, display: "flex", flexDirection: "column", gap: ".2rem" }}>
              {fresh.slice(0, 5).map((n) => <span key={n.id} style={small}>{n.line}</span>)}
            </div>
          ) : null}
          {feed && !feed.length ? (
            <Text dim>{(data.friends || []).length || (data.follows || []).length
              ? text("feedQuiet", "Nobody you follow has posted yet.")
              : text("feedEmpty", "Your feed fills up once you add friends or follow a wall.")}</Text>
          ) : null}
          {(feed || []).map((p) => <Post key={`${p.house}/${p.id}`} p={p} reload={fetchFeed} />)}
          {missed.length ? <Text dim>{text("missed", "Not reachable right now: {houses}").replace("{houses}", missed.join(", "))}</Text> : null}
        </div>
      ) : null}

      {tab === "wall" ? (
        <div>
          {me.link ? <div style={{ ...small, overflowWrap: "anywhere" }}>{me.link}</div> : null}
          {me.bio ? <Text>{me.bio}</Text> : null}
          <Stats>
            <Stat value={(data.wall || []).length} label={text("posts", "Posts")} />
            <Stat value={(data.friends || []).length} label={text("friends", "Friends")} />
            <Stat value={(data.followers || []).length} label={text("followers", "Followers")} />
          </Stats>
          {!(data.wall || []).length ? <Text dim>{text("wallEmpty", "Nothing on your wall yet.")}</Text> : null}
          {(data.wall || []).map((p) => <Post key={p.id} p={p} own reload={load} />)}
        </div>
      ) : null}

      {tab === "friends" ? (
        <div>
          {asked.map((r) => (
            <div key={r.house} style={box}>
              <div style={{ overflowWrap: "anywhere" }}>
                {text("wants", "{name} wants to be friends").replace("{name}", r.name ? `${r.name} (${r.house})` : r.house)}
              </div>
              <Buttons>
                <Button primary onClick={() => act(`accept ${r.house}`)}>{text("accept", "Accept")}</Button>
                <Button onClick={() => act(`decline ${r.house}`)}>{text("decline", "Decline")}</Button>
              </Buttons>
            </div>
          ))}
          <div style={box}>
            <div style={{ display: "flex", gap: ".4rem", alignItems: "center", flexWrap: "wrap" }}>
              <input style={{ ...field, flex: "1 1 10rem" }} value={who} placeholder={text("houseHint", "Their house, like anna")}
                     onInput={(e) => setWho(e.currentTarget.value.trim().toLowerCase())} />
              <Buttons>
                <Button primary onClick={() => { if (who) void act(`add ${who}`).then(() => setWho("")); }}>{text("add", "Add friend")}</Button>
                <Button onClick={() => { if (who) void act(`follow ${who}`).then(() => setWho("")); }}>{text("follow", "Follow")}</Button>
              </Buttons>
            </div>
          </div>
          {[["friends", data.friends, "remove", text("unfriend", "Unfriend")],
            ["following", data.follows, "unfollow", text("unfollow", "Unfollow")],
            ["followers", data.followers, "", ""]].map(([key, list, verb, word]) => (
            <div key={key} style={box}>
              <div style={{ ...small, textTransform: "uppercase", letterSpacing: ".06em" }}>
                {text(key, key)} · {(list || []).length}
              </div>
              {(list || []).map((f) => (
                <div key={f.house} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".5rem", flexWrap: "wrap" }}>
                  <span style={{ overflowWrap: "anywhere" }}>{f.name || f.house} <span style={small}>{f.house}</span></span>
                  {verb ? <Button onClick={() => act(`${verb} ${f.house}`)}>{word}</Button> : null}
                </div>
              ))}
            </div>
          ))}
          {(data.sent || []).length ? (
            <Text dim>{text("waiting", "Waiting for an answer: {houses}").replace("{houses}", data.sent.map((s) => s.house).join(", "))}</Text>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
};
