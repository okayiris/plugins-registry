export default () => {
  const [mail, setMail] = useState(null);
  const [agenda, setAgenda] = useState(null);
  const [view, setView] = useState("overview");
  const [open, setOpen] = useState(null);
  const [busy, setBusy] = useState(true);
  const [readAt, setReadAt] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  const INBOX = 50;
  const SHOWN = 20;
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
  // An invitation sits in the text (some mail programs put the .ics there) or in an attachment.
  const invitation = (x) => {
    if (!x) return false;
    const inText = [x.text, x.body, x.ics].some((p) => typeof p === "string" && p.indexOf("BEGIN:VCALENDAR") >= 0);
    const attached = (x.attachments || []).some((a) => a && (String(a.type || a.contentType || "").toLowerCase().indexOf("calendar") >= 0
      || String(a.name || a.filename || "").toLowerCase().endsWith(".ics")));
    return inText || attached;
  };
  const readable = (t) => String(t || "").replace(/BEGIN:VCALENDAR[\s\S]*?(END:VCALENDAR|$)/g, "[" + text("invitationMark", "calendar invitation") + "]").trim();

  // The coming meetings come from the calendar plugin, through this plugin's own command
  // (`mailbox agenda`), the way the house's own screens reach their command. Without the calendar the
  // mail still reads; the card says what is missing.
  const run = async (args) => {
    const r = await fetch("/commands/run", { method: "POST", body: JSON.stringify({ cmd: "mailbox", args: args + " --json" }) });
    const d = await r.json();
    const body = d && (d.tekst ?? d.text ?? d.output);
    let out;
    try { out = JSON.parse(body); } catch (e) { throw new Error(body || text("noAnswer", "No answer.")); }
    if (out.error) throw new Error(out.error);
    return out;
  };

  const loadAgenda = async () => {
    try {
      setAgenda(await run("agenda"));
    } catch (e) {
      setAgenda({ installed: true, error: String((e && e.message) || e), meetings: [], invites: [] });
    }
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
        fetch("/mail/inbox?n=" + INBOX, { cache: "no-store" }).then((r) => {
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
      void loadAgenda();
    } catch (e) {
      setError(String((e && e.message) || e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const frame = (children) => (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem", padding: "0.5rem", maxWidth: "min(92vw, 36rem)" }}>
      {children}
    </div>
  );

  // One mail, full text. Sent mail has no text in this house: the bridge keeps only when and to whom.
  // A received mail with an invitation can go into the calendar from here.
  if (open) {
    const kind = open.kind;
    const item = open.item;
    const heading = kind === "sent" ? text("sentTitle", "Sent by this house")
      : kind === "draft" ? text("openDrafts", "Open drafts") : text("inbox", "Inbox");
    const body = kind === "sent"
      ? text("noText", "This house keeps no text for sent mail; the bridge stores only when it went and to whom.")
      : (readable(item.text || item.body) || text("noBody", "(no text)"));
    const invite = kind === "inbox" && invitation(item);
    const calendar = agenda && agenda.installed;
    return frame(
      <Card label={heading} title={item.subject || text("noSubject", "(no subject)")} icon="mail">
        {kind === "inbox" && <Row left={text("from", "From")} right={item.from || ""} />}
        {addresses(item.to) ? <Row left={text("to", "To")} right={addresses(item.to)} /> : null}
        {stamp(item.sentAt || item.at) ? <Row left={text("date", "Date")} right={stamp(item.sentAt || item.at)} /> : null}
        <Row left={text("id", "Id")} right={String(item.id || "")} />
        <Text>{body}</Text>
        {invite ? (
          <Text dim>{calendar ? text("hasInvite", "This mail carries a calendar invitation.")
            : text("hasInviteNoCal", "This mail carries a calendar invitation. With the calendar plugin it goes in the calendar from here.")}</Text>
        ) : null}
        <Buttons>
          <Button outline onClick={() => { setOpen(null); setDone(""); setError(""); }}>{text("back", "Back")}</Button>
          {invite && calendar ? (
            <Button primary onClick={async () => {
              setError("");
              setDone("");
              try {
                const out = await run("accept " + item.id);
                setDone((out.done === "cancelled" ? text("tookOut", "Taken out of the calendar")
                  : out.done === "updated" ? text("updated", "Updated in the calendar") : text("added", "In the calendar"))
                  + ": " + ((out.meeting && out.meeting.title) || item.subject || ""));
                void loadAgenda();
              } catch (e) {
                setError(String((e && e.message) || e));
              }
            }}>{text("accept", "Put in calendar")}</Button>
          ) : null}
        </Buttons>
        {error || done ? <Text dim>{error ? text("failed", "That did not work") + ": " + error : done}</Text> : null}
      </Card>
    );
  }

  const header = (
    <Card label={text("label", "Mailbox")} title={mail && mail.address ? mail.address : text("title", "The mailbox of this house")} icon="mail">
      <Text dim>{text("intro", "Everything this house received and sent. Read-only: nothing here sends and nothing here makes a draft.")}</Text>
      {mail && (
        <Stats>
          <Stat value={mail.inbox.length >= INBOX ? INBOX + "+" : mail.inbox.length} label={text("received", "received")} />
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

  // Nothing read yet, or reading failed: the header and the reason, never a view of mail that is not there.
  if (!mail) return frame([header, actions]);

  const row = (kind, item, left, right, key) => (
    <Button outline key={key} onClick={() => { setDone(""); setError(""); setOpen({ kind, item }); }}>
      {short(left, 74) + "   " + short(right, 46)}
    </Button>
  );

  const list = (kind, items, empty, left, right, max) => (
    items.length === 0 ? <Text dim>{empty}</Text> : (
      <div style={{ display: "grid", gap: "0.4rem", paddingTop: "0.3rem" }}>
        {items.slice(0, max).map((x, i) => row(kind, x, left(x), right(x), String(x.id || i)))}
        {items.length > max ? <Text dim>{text("more", "And {n} more; ask Iris for older mail.").replace("{n}", String(items.length - max))}</Text> : null}
      </div>
    )
  );

  // Mark a mail that carries an invitation, unless its subject already says so.
  const subject = (x) => {
    const s = x.subject || text("noSubject", "(no subject)");
    const said = s.toLowerCase().indexOf(text("invitationShort", "Invitation").toLowerCase()) >= 0 || /invitation|uitnodiging/i.test(s);
    return (invitation(x) && !said ? text("invitationShort", "Invitation") + ": " : "") + s;
  };
  const received = (max) => list("inbox", mail.inbox, text("emptyInbox", "No mail yet."),
    (x) => stamp(x.at) + "  " + (x.from || ""), subject, max);

  const coming = () => {
    if (!agenda) return <Text dim>{text("readingAgenda", "Reading the calendar")}</Text>;
    if (!agenda.installed) return <Text dim>{text("noCalendar", "With the calendar plugin, your meetings and the invitations in your mail show here.")}</Text>;
    if (agenda.error) return <Text dim>{text("agendaFailed", "The calendar could not be read") + ": " + agenda.error}</Text>;
    const waiting = (agenda.invites || []).filter((x) => x.state === "new" || x.state === "changed");
    return (
      <div style={{ display: "grid", gap: "0.3rem" }}>
        {agenda.meetings.length === 0 ? <Text dim>{text("nothingPlanned", "Nothing planned in the next 7 days.")}</Text>
          : agenda.meetings.slice(0, 5).map((m) => (
            <Row key={m.id} left={m.starts.slice(0, 10) + " " + m.starts.slice(11, 16)} right={m.title + (m.place ? ", " + m.place : "")} />
          ))}
        {waiting.length ? <Text dim>{text("waiting", "Invitations not in the calendar yet") + ": " + waiting.map((x) => x.title).join(", ")}</Text> : null}
      </div>
    );
  };

  return frame([
    header,
    actions,
    view === "overview" ? (
      <Card key="received" label={text("inbox", "Inbox")} title={text("latestReceived", "Latest received")} icon="mail">
        {received(5)}
      </Card>
    ) : null,
    view === "overview" ? (
      <Card key="coming" label={text("calendarLabel", "Calendar")} title={text("comingUp", "Coming up")} icon="calendar">
        {coming()}
      </Card>
    ) : null,
    view === "overview" ? (
      <Card key="drafts" label={text("draftsLabel", "Drafts")} title={text("openDrafts", "Open drafts")} icon="mail">
        {list("draft", mail.drafts, text("noDrafts", "No open draft."), (x) => addresses(x.to), (x) => x.subject || "", SHOWN)}
      </Card>
    ) : null,
    view === "inbox" ? (
      <Card key="inbox" label={text("inbox", "Inbox")} title={text("receivedTitle", "Received by this house")} icon="mail">
        {received(SHOWN)}
      </Card>
    ) : null,
    view === "sent" ? (
      <Card key="sent" label={text("sentLabel", "Sent")} title={text("sentTitle", "Sent by this house")} icon="mail">
        {list("sent", mail.sent, text("emptySent", "No mail sent yet."),
          (x) => stamp(x.sentAt || x.at) + "  " + addresses(x.to), (x) => x.subject || "", SHOWN)}
      </Card>
    ) : null,
  ]);
};
