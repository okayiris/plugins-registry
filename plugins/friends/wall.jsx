// The wall on the house's own address (/wall), open to everyone: who lives here, and the posts they made
// public. Friends-only posts, who liked what and the comments never show here; friends see those in
// their own Iris. The page talks only to its own command through pageApi.

const count = (n, one, many) => (n === 1 ? one : many).replace("{n}", n);

const since = (at) => {
  const lang = document.documentElement.lang || undefined;
  try {
    return new Date(at * 1000).toLocaleDateString(lang, { day: "numeric", month: "long", year: "numeric" });
  } catch (e) {
    return new Date(at * 1000).toLocaleDateString();
  }
};

const Photo = ({ id }) => {
  const [src, setSrc] = useState("");
  useEffect(() => {
    let live = true;
    void pageApi({ action: "photo", id }).then((d) => {
      if (live && d && d.data) setSrc(`data:${d.type};base64,${d.data}`);
    });
    return () => { live = false; };
  }, [id]);
  return src ? (
    <img src={src} alt="" loading="lazy"
         style={{ width: "100%", maxHeight: "36rem", objectFit: "cover", display: "block", borderRadius: ".8rem", marginTop: ".6rem" }} />
  ) : (
    <div style={{ width: "100%", aspectRatio: "4 / 3", maxHeight: "36rem", borderRadius: ".8rem", marginTop: ".6rem",
                  background: "var(--glass)", border: "1px solid var(--edge)" }} />
  );
};

export default () => {
  const [profile, setProfile] = useState(null);
  const [posts, setPosts] = useState([]);
  const [more, setMore] = useState(false);
  const [problem, setProblem] = useState("");
  const [avatar, setAvatar] = useState("");

  const page = async (before) => {
    const d = await pageApi({ action: "posts", before: before || 0, limit: 12 });
    if (d && Array.isArray(d.posts)) {
      setPosts((was) => (before ? [...was, ...d.posts] : d.posts));
      setMore(!!d.more);
    } else setProblem(text("wallUnavailable", "This wall cannot be reached right now. Try again in a moment."));
  };

  useEffect(() => {
    void pageApi({ action: "profile" }).then((p) => {
      if (p && !p.error) {
        setProfile(p);
        if (p.avatar) void pageApi({ action: "photo", id: "avatar" }).then((a) => { if (a && a.data) setAvatar(`data:${a.type};base64,${a.data}`); });
      } else setProblem(text("wallUnavailable", "This wall cannot be reached right now. Try again in a moment."));
    });
    void page(0);
  }, []);

  const name = (profile && (profile.name || profile.house)) || text("wallTitle", "Wall");
  const counts = profile ? [
    count(profile.posts, text("postOne", "{n} post"), text("postsN", "{n} posts")),
    count(profile.friends, text("friendOne", "{n} friend"), text("friendsN", "{n} friends")),
    count(profile.followers, text("followerOne", "{n} follower"), text("followersN", "{n} followers")),
  ].join(" · ") : "";

  return (
    <Screen title={name} subtitle={counts}>
      <div style={{ maxWidth: "36rem" }}>
        {profile && (avatar || profile.bio) ? (
          <div style={{ display: "flex", gap: ".9rem", alignItems: "center", margin: ".4rem 0 1rem" }}>
            {avatar ? (
              <img src={avatar} alt="" style={{ width: "4rem", height: "4rem", borderRadius: "50%", objectFit: "cover", flex: "none" }} />
            ) : null}
            {profile.bio ? <span style={{ color: "var(--dim)", overflowWrap: "anywhere", whiteSpace: "pre-line" }}>{profile.bio}</span> : null}
          </div>
        ) : null}
        {problem ? <Text>{problem}</Text> : null}
        {profile && !posts.length && !problem ? <Text dim>{text("nothingPublic", "Nothing shared with everyone yet.")}</Text> : null}
        {posts.map((p) => (
          <Card key={p.id}>
            <div style={{ color: "var(--dim)", fontSize: ".82rem" }}>{since(p.at)}</div>
            {p.text ? <div style={{ whiteSpace: "pre-line", marginTop: ".3rem", overflowWrap: "anywhere" }}>{p.text}</div> : null}
            {p.photo ? <Photo id={p.id} /> : null}
            {p.likes || p.comments ? (
              <div style={{ color: "var(--dim)", fontSize: ".82rem", marginTop: ".5rem" }}>
                {[p.likes ? count(p.likes, text("likeOne", "{n} like"), text("likesN", "{n} likes")) : "",
                  p.comments ? count(p.comments, text("commentOne", "{n} comment"), text("commentsN", "{n} comments")) : ""].filter(Boolean).join(" · ")}
              </div>
            ) : null}
          </Card>
        ))}
        {more ? (
          <Buttons><Button onClick={() => page(posts[posts.length - 1].id)}>{text("more", "Older posts")}</Button></Buttons>
        ) : null}
        {profile ? (
          <Text dim>
            {text("howFriends", "Friends see more of {name} in their own Iris. Have an Iris? Say to her: add {house} as a friend.")
              .replace("{name}", name).replace("{house}", profile.house || "")}
          </Text>
        ) : null}
      </div>
    </Screen>
  );
};
