export default () => {
  const [mail, setMail] = useState(null);
  const [view, setView] = useState("overview");
  const [open, setOpen] = useState(null);
  const [busy, setBusy] = useState(true);
  const [readAt, setReadAt] = useState("");
  const [error, setError] = useState("");

  const two = (n) => String(n).padStart(2, "0");
  const stamp = (v) => {
    if (v === undefined || v === null || v === "") return "";
    const d = typeof v === "number" ? new Date(v) : new Date(String(v));
    if (isNaN(d.getTime())) return String(v);
    return d.getFullYear() + "-" + two(d.getMonth() + 1) + "-" + two(d.getDate())
      + " " + two(d.getHours()) + ":" + two(d.getMinutes());
  };
  const clock = (d) => two(d.getHours()) + ":" + two(d.getMinutes());
  const addresses = (v) => (Array.isArray(v) ? v.join(", ") : String(v || ""));
  const short = (s, n) => {
    const t = String(s || "").replace(/\s+/g, " ").trim();
    return t.length > n ? t.slice(0, n - 3) + "..." : t;
  };

  // Read both lists from this house's own bridge, with this window's own fetch. A window may read /mail,
  // the same way it may read /socials (see src/herkomst.ts in the house): the page hands every window the
  // secret of this bridge, so this is a real read and nothing about it goes to the conversation.
  const load = async () => {
    setBusy(true);
    setError("");
    try {
      const [overview, inbox] = await Promise.all([
        fetch("/mail", { cache: "no-store" }).then((r) => {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        }),
        fetch("/mail/inbox?n=50", { cache: "no-store" }).then((r) => {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        }),
      ]);
      setMail({
        address: overview.address || "",
        drafts: overview.drafts || [],
        sent: overview.sent || [],
        inbox: inbox.mail || [],
      });
      setReadAt(clock(new Date()));
    } catch (e) {
      setError(String((e && e.message) || e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { void load(); }, []);

  // One mail, full text. Sent mail has no text in this house: the bridge keeps only when and to whom.
  if (open) {
    const kind = open.kind;
    const item = open.item;
    const heading = kind === "sent" ? text("sent", "Sent")
      : kind === "draft" ? text("drafts", "Drafts") : text("inbox", "Inbox");
    const body = kind === "sent"
      ? text("noText", "This house keeps no text for sent mail; the bridge stores only when it went and to whom.")
      : (item.text || item.body || text("noBody", "(no text)"));
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem", padding: "0.5rem", maxWidth: "min(92vw, 36rem)" }}>
        <Card label={heading} title={item.subject || text("noSubject", "(no subject)")} icon="mail">
          {kind === "inbox" && <Row left={text("from", "From")} right={item.from || ""} />}
          <Row left={text("to", "To")} right={addresses(item.to)} />
          <Row left={text("date", "Date")} right={stamp(item.sentAt || item.at)} />
          <Row left={text("id", "Id")} right={String(item.id || "")} />
          <Text>{body}</Text>
          <Buttons>
            <Button outline onClick={() => setOpen(null)}>{text("back", "Back")}</Button>
          </Buttons>
        </Card>
      </div>
    );
  }

  const header = (
    <Card label={text("label", "Mailbox")} title={mail && mail.address ? mail.address : text("title", "The mailbox of this house")} icon="mail">
      <Text dim>{text("intro", "Everything this house received and sent. Read-only: nothing here sends and nothing here makes a draft.")}</Text>
      {mail && (
        <Stats>
          <Stat value={mail.inbox.length} label={text("received", "received")} />
          <Stat value={mail.sent.length} label={text("sent", "sent")} />
          <Stat value={mail.drafts.length} label={text("drafts", "drafts")} />
        </Stats>
      )}
    </Card>
  );

  // Every button below does its own work here: the three views rearrange this window, Reload reads the
  // bridge again. The answer shows next to the buttons (when it was read, or what went wrong), never only
  // in the conversation (DESIGN.md, "the result next to the button").
  const actions = (
    <Card label={text("read", "Read")} title={readAt ? text("readAt", "Read at") + " " + readAt : text("reading", "Reading the mailbox")}>
      <Buttons>
        <Button outline uit={busy} onClick={() => void load()}>{busy ? "..." : text("reload", "Reload")}</Button>
        <Button primary={view === "overview"} outline={view !== "overview"} onClick={() => setView("overview")}>{text("overview", "Overview")}</Button>
        <Button primary={view === "inbox"} outline={view !== "inbox"} onClick={() => setView("inbox")}>{text("recent", "Recent received")}</Button>
        <Button primary={view === "sent"} outline={view !== "sent"} onClick={() => setView("sent")}>{text("latest", "Latest sent")}</Button>
      </Buttons>
      {error ? <Text dim>{text("cantRead", "This window cannot read the mailbox") + ": " + error}</Text> : null}
    </Card>
  );

  if (busy && !mail) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem", padding: "0.5rem", maxWidth: "min(92vw, 36rem)" }}>
        {header}
        {actions}
      </div>
    );
  }

  const row = (kind, item, left, right, key) => (
    <Button outline key={key} onClick={() => setOpen({ kind, item })}>
      {short(left, 74) + "   " + short(right, 46)}
    </Button>
  );

  const list = (kind, items, empty, left, right) => (
    items.length === 0 ? <Text dim>{empty}</Text> : (
      <div style={{ display: "grid", gap: "0.4rem", paddingTop: "0.3rem" }}>
        {items.slice(0, 20).map((x, i) => row(kind, x, left(x), right(x), String(x.id || i)))}
      </div>
    )
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem", padding: "0.5rem", maxWidth: "min(92vw, 36rem)" }}>
      {header}
      {actions}

      {view === "inbox" && (
        <Card label={text("inbox", "Inbox")} title={text("received", "Received")} icon="mail">
          {list("inbox", mail.inbox, text("emptyInbox", "No mail yet."),
            (x) => stamp(x.at) + "  " + (x.from || ""), (x) => x.subject || "")}
        </Card>
      )}

      {view === "sent" && (
        <Card label={text("sent", "Sent")} title={text("sentTitle", "Sent by this house")} icon="mail">
          {list("sent", mail.sent, text("emptySent", "No mail sent yet."),
            (x) => stamp(x.sentAt || x.at) + "  " + addresses(x.to), (x) => x.subject || "")}
        </Card>
      )}

      {view === "overview" && (
        <Card label={text("drafts", "Drafts")} title={text("openDrafts", "Open drafts")} icon="mail">
          {list("draft", mail.drafts, text("noDrafts", "No open draft."), (x) => addresses(x.to), (x) => x.subject || "")}
        </Card>
      )}
    </div>
  );
};
