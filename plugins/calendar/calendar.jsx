export default () => {
  const [data, setData] = useState(null);
  const [view, setView] = useState("agenda");
  const [open, setOpen] = useState(null);
  const [busy, setBusy] = useState(true);
  const [readAt, setReadAt] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  const [sure, setSure] = useState(false);
  const [form, setForm] = useState({ title: "", date: "", time: "", minutes: "60", guests: "", place: "", note: "" });

  const two = (n) => String(n).padStart(2, "0");
  const clock = (d) => two(d.getHours()) + ":" + two(d.getMinutes());
  const hour = (s) => String(s || "").slice(11, 16);
  const day = (s) => String(s || "").slice(0, 10);
  const dayLabel = (iso, today) => {
    if (iso === today) return text("today", "Today");
    const t = new Date(today + "T12:00");
    t.setDate(t.getDate() + 1);
    const tomorrow = t.getFullYear() + "-" + two(t.getMonth() + 1) + "-" + two(t.getDate());
    if (iso === tomorrow) return text("tomorrow", "Tomorrow");
    const d = new Date(iso + "T12:00");
    return isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
  };
  const longDate = (iso) => {
    const d = new Date(iso + "T12:00");
    return isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  };
  const span = (m) => hour(m.starts) + " - " + hour(m.ends);
  // Words go to the command through the house, split on spaces and quotes, so a text is quoted and
  // loses its own double quotes.
  const quote = (s) => "\"" + String(s || "").replace(/"/g, "'").replace(/\s+/g, " ").trim() + "\"";

  // The window asks its own command, like the house's own screens do (/commands/run).
  const run = async (args) => {
    const r = await fetch("/commands/run", { method: "POST", body: JSON.stringify({ cmd: "calendar", args: args + " --json" }) });
    const d = await r.json();
    const body = d && (d.tekst ?? d.text ?? d.output);
    let out;
    try { out = JSON.parse(body); } catch (e) { throw new Error(body || text("noAnswer", "The calendar did not answer.")); }
    if (out.error) throw new Error(out.error);
    return out;
  };

  const load = async () => {
    setBusy(true);
    setError("");
    try {
      const [week, now] = await Promise.all([run("week 14"), run("")]);
      setData({ today: week.today, meetings: week.meetings || [], invites: now.invites || [], mailNote: now.mailNote || "" });
      setReadAt(clock(new Date()));
    } catch (e) {
      setError(String((e && e.message) || e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const act = async (args, message) => {
    setError("");
    setDone("");
    try {
      const out = await run(args);
      await load();
      setDone(message(out));
      return out;
    } catch (e) {
      setError(String((e && e.message) || e));
      return null;
    }
  };

  const frame = (children) => (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem", padding: "0.5rem", maxWidth: "min(92vw, 36rem)" }}>
      {children}
    </div>
  );
  const note = (error || done) ? <Text dim>{error ? text("failed", "That did not work") + ": " + error : done}</Text> : null;
  const field = { width: "100%", boxSizing: "border-box", padding: "0.45rem 0.6rem", borderRadius: "0.6rem",
    border: "1px solid var(--edge)", background: "var(--glass)", color: "var(--fg)", font: "inherit" };
  const input = (key, label, type) => (
    <label style={{ display: "grid", gap: "0.2rem", minWidth: 0 }}>
      <span style={{ color: "var(--dim)", fontSize: "0.85em" }}>{label}</span>
      <input type={type || "text"} value={form[key]} style={field}
        onInput={(e) => setForm({ ...form, [key]: e.currentTarget.value })} />
    </label>
  );

  // One meeting: what, when, where, who. Your own meetings can be cancelled and their invitation made
  // into a mail draft; a meeting from someone else's invitation is answered by replying to their mail.
  if (open) {
    const m = open.meeting;
    const own = m.source !== "mail";
    const inv = open.invitation;
    return frame(
      <Card label={own ? text("ownMeeting", "Your meeting") : text("invited", "Invited by") + " " + (m.organizer || "")}
        title={m.title} icon="calendar">
        <Row left={text("when", "When")} right={dayLabel(day(m.starts), data ? data.today : day(m.starts)) + ", " + span(m)} />
        {m.place ? <Row left={text("where", "Where")} right={m.place} /> : null}
        {m.guests.length ? <Row left={text("guests", "Guests")} right={m.guests.join(", ")} /> : null}
        {m.note ? <Text>{m.note}</Text> : null}
        {m.status === "cancelled" ? <Text dim>{text("cancelled", "Cancelled.")}</Text> : null}
        {own && inv ? (
          <div style={{ display: "grid", gap: "0.3rem", paddingTop: "0.3rem" }}>
            <Text dim>{text("invitationFor", "The invitation for") + " " + inv.to.join(", ") + ": " + inv.subject}</Text>
          </div>
        ) : null}
        <Buttons>
          <Button outline onClick={() => { setOpen(null); setSure(false); setDone(""); setError(""); }}>{text("back", "Back")}</Button>
          {own && inv && m.status !== "cancelled" ? (
            <Button primary say={"Make a mail draft of the invitation for calendar meeting " + m.id + " (calendar invitation " + m.id + ")."}
              onClick={() => setDone(text("draftAsked", "Iris makes it a mail draft. You press Send on your screen."))}>
              {text("mailInvite", "Mail the invitation")}
            </Button>
          ) : null}
          {m.status !== "cancelled" ? (
            <Button outline onClick={async () => {
              if (!sure) { setSure(true); setDone(text("sure", "Press once more to cancel it.")); return; }
              setSure(false);
              const out = await act("cancel " + m.id, () => text("cancelDone", "Cancelled."));
              if (out && out.meeting) setOpen({ meeting: out.meeting, invitation: out.invitation });
            }}>{sure ? text("cancelSure", "Yes, cancel it") : text("cancel", "Cancel meeting")}</Button>
          ) : null}
        </Buttons>
        {note}
      </Card>
    );
  }

  const header = (
    <Card label={text("label", "Calendar")} title={data ? longDate(data.today) : text("title", "The calendar of this house")} icon="calendar">
      {data ? (
        <Stats>
          <Stat value={data.meetings.filter((m) => day(m.starts) === data.today).length} label={text("statToday", "today")} />
          <Stat value={data.meetings.length} label={text("statAhead", "next 14 days")} />
          <Stat value={data.invites.filter((x) => x.state === "new" || x.state === "changed").length} label={text("statInvites", "invitations")} />
        </Stats>
      ) : <Text dim>{text("intro", "Meetings you plan here and invitations from the mailbox, in one calendar.")}</Text>}
    </Card>
  );

  const actions = (
    <Card label={text("read", "Read")} title={readAt ? text("readAt", "Read at") + " " + readAt : text("reading", "Reading the calendar")}>
      <Buttons>
        <Button outline uit={busy} onClick={() => void load()}>{busy ? "..." : text("reload", "Reload")}</Button>
        <Button primary={view === "agenda"} outline={view !== "agenda"} onClick={() => setView("agenda")}>{text("agenda", "Agenda")}</Button>
        <Button primary={view === "plan"} outline={view !== "plan"} onClick={() => setView("plan")}>{text("plan", "Plan a meeting")}</Button>
        <Button primary={view === "invites"} outline={view !== "invites"} onClick={() => setView("invites")}>{text("invites", "Invitations")}</Button>
      </Buttons>
      {note}
    </Card>
  );

  if (!data) return frame([header, actions]);

  const openMeeting = async (id) => {
    try {
      const out = await run("show " + id);
      setDone("");
      setOpen(out);
    } catch (e) {
      setError(String((e && e.message) || e));
    }
  };

  const days = [];
  for (const m of data.meetings) {
    const d = day(m.starts);
    if (!days.length || days[days.length - 1].day !== d) days.push({ day: d, items: [] });
    days[days.length - 1].items.push(m);
  }

  const agenda = (
    <Card label={text("agenda", "Agenda")} title={text("ahead", "The next 14 days")} icon="calendar">
      {days.length === 0 ? <Text dim>{text("empty", "Nothing planned.")}</Text> : days.map((d) => (
        <div key={d.day} style={{ display: "grid", gap: "0.35rem", paddingTop: "0.4rem" }}>
          <Text dim>{dayLabel(d.day, data.today)}</Text>
          {d.items.map((m) => (
            <Button outline key={m.id} onClick={() => openMeeting(m.id)}>
              {span(m) + "   " + m.title + (m.place ? ", " + m.place : "")}
            </Button>
          ))}
        </div>
      ))}
    </Card>
  );

  const plan = (
    <Card label={text("plan", "Plan a meeting")} title={text("planTitle", "A new meeting")} icon="calendar">
      <div style={{ display: "grid", gap: "0.5rem", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 10rem), 1fr))" }}>
        {input("title", text("what", "What"))}
        {input("date", text("date", "Date"), "date")}
        {input("time", text("time", "Time"), "time")}
        {input("minutes", text("minutes", "Minutes"), "number")}
        {input("guests", text("with", "Guests (mail addresses)"))}
        {input("place", text("where", "Where"))}
        {input("note", text("noteField", "Note"))}
      </div>
      <Buttons>
        <Button primary uit={!form.title.trim() || !form.date || !form.time} onClick={async () => {
          let args = "meet " + quote(form.title) + " " + form.date + " " + form.time;
          if (form.minutes) args += " --minutes " + String(parseInt(form.minutes, 10) || 60);
          if (form.guests.trim()) args += " --with " + quote(form.guests);
          if (form.place.trim()) args += " --where " + quote(form.place);
          if (form.note.trim()) args += " --note " + quote(form.note);
          const out = await act(args, (o) => text("planned", "Planned") + ": " + o.meeting.title + ", "
            + dayLabel(day(o.meeting.starts), data.today) + " " + span(o.meeting)
            + (o.clashes && o.clashes.length ? ". " + text("overlaps", "It overlaps with") + " " + o.clashes.map((c) => c.title).join(", ") : ""));
          if (out && out.meeting) {
            setForm({ title: "", date: "", time: "", minutes: "60", guests: "", place: "", note: "" });
            setOpen({ meeting: out.meeting, invitation: out.invitation });
          }
        }}>{text("planButton", "Plan it")}</Button>
      </Buttons>
      <Text dim>{text("planHelp", "With guests, the invitation is ready as a mail draft from this house's mailbox; nothing is sent until you press Send.")}</Text>
    </Card>
  );

  const invites = (
    <Card label={text("invites", "Invitations")} title={text("invitesTitle", "In the mailbox")} icon="mail">
      {data.mailNote ? <Text dim>{text("noMail", "The mailbox could not be read") + ": " + data.mailNote}</Text> : null}
      {data.invites.length === 0 && !data.mailNote ? <Text dim>{text("noInvites", "No invitations in the mailbox.")}</Text> : null}
      {data.invites.map((x, i) => (
        <div key={x.mailId + i} style={{ display: "grid", gap: "0.3rem", paddingTop: "0.4rem" }}>
          <Row left={x.title} right={x.cancelled ? text("cancelledShort", "cancelled") : dayLabel(day(x.starts), data.today) + " " + hour(x.starts)} />
          <Text dim>{text("from", "From") + " " + (x.sender || x.organizer) + (x.place ? ", " + x.place : "")}</Text>
          {x.state === "new" || x.state === "changed" ? (
            <Buttons>
              <Button outline onClick={() => act("accept " + x.mailId, (o) => (o.done === "cancelled"
                ? text("tookOut", "Taken out of the calendar") : text("added", "In the calendar")) + ": " + x.title)}>
                {x.cancelled ? text("takeOut", "Take it out") : x.state === "changed" ? text("update", "Update") : text("accept", "Put in calendar")}
              </Button>
            </Buttons>
          ) : <Text dim>{x.state === "cancelled" ? text("cancelled", "Cancelled.") : text("inCalendar", "In the calendar.")}</Text>}
        </div>
      ))}
    </Card>
  );

  return frame([header, actions, view === "agenda" ? agenda : view === "plan" ? plan : invites]);
};
