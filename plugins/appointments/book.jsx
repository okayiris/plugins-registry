// The booking page on the house's own address (/book): pick a kind of appointment, a day and a time (or a
// webinar session), leave a name and an e-mail, and get a confirmation with the video link or the address,
// a calendar file and a way to cancel. A booking is shown only with its own token from its own link.

export default () => {
  const params = new URLSearchParams(window.location.search);
  const [info, setInfo] = useState(null);
  const [step, setStep] = useState(params.get("booking") ? "done" : "types");
  const [type, setType] = useState(null);
  const [days, setDays] = useState([]);
  const [day, setDay] = useState(null);
  const [slot, setSlot] = useState(null);
  const [session, setSession] = useState(null);
  const [form, setForm] = useState({ name: "", email: "", note: "" });
  const [problem, setProblem] = useState("");
  const [booked, setBooked] = useState(null);
  const [sure, setSure] = useState(false);

  const load = async () => {
    const data = await pageApi({ action: "types" });
    if (data && data.types) setInfo(data);
    else setProblem(text("unavailable", "The booking page cannot be reached right now. Try again in a moment."));
  };

  const view = async (action) => {
    const data = await pageApi({ action, booking: params.get("booking"), token: params.get("token") });
    setBooked(data && !data.error ? data : { error: true });
  };

  useEffect(() => {
    void load();
    if (params.get("booking")) void view("view");
  }, []);

  // Times are the host's own: a slot is "HH:MM" on a day, a session or booking an ISO time with its offset.
  const dayLabel = (iso) => {
    const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(document.documentElement.lang || undefined,
      { weekday: "long", day: "numeric", month: "long" });
  };
  const clock = (iso) => iso.slice(11, 16);
  const kindLabel = (t) => ({
    place: t.place ? `${text("atPlace", "At")} ${t.place}` : text("inPerson", "In person"),
    video: text("video", "Video call"),
    webinar: text("webinar", "Webinar"),
  }[t.kind]);

  const pick = async (t) => {
    setType(t);
    setProblem("");
    setDay(null);
    setSlot(null);
    setSession(null);
    if (t.kind === "webinar") {
      setStep("session");
      return;
    }
    setStep("time");
    const data = await pageApi({ action: "slots", type: t.id });
    const found = (data && data.days) || [];
    setDays(found);
    if (found.length) setDay(found[0].day);
  };

  const confirm = async () => {
    setProblem("");
    const data = await pageApi({
      action: "book", type: type.id, day, time: slot, session: session && session.id,
      name: form.name, email: form.email, note: form.note,
    });
    if (!data || data.error) {
      const why = {
        guest: text("needGuest", "Fill in your name and a valid e-mail address."),
        taken: text("taken", "That moment was just taken. Pick another one."),
        full: text("full", "This session is full."),
        twice: text("twice", "You already have a seat in this session."),
        closed: text("closed", "No bookings can be made right now."),
      }[data && data.error] || text("failed", "Booking did not work. Try again in a moment.");
      setProblem(why);
      if (data && data.error === "taken") void pick(type);
      return;
    }
    // A link to this booking, so the guest can come back to it (and cancel) from the browser's history.
    window.history.replaceState(null, "", `${window.location.pathname}?booking=${data.booking}&token=${data.token}`);
    params.set("booking", data.booking);
    params.set("token", data.token);
    setBooked(data);
    setStep("done");
  };

  const calendar = (b) => {
    const stamp = (iso) => new Date(iso).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
    const where = b.place || b.link || "";
    const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Iris//appointments//EN", "BEGIN:VEVENT",
      `UID:booking-${b.booking}@iris`, `DTSTAMP:${stamp(new Date().toISOString())}`,
      `DTSTART:${stamp(b.starts)}`, `DTEND:${stamp(b.ends)}`,
      `SUMMARY:${b.type}${b.host ? ` - ${b.host}` : ""}`, where ? `LOCATION:${where}` : "",
      b.link ? `DESCRIPTION:${b.link}` : "", "END:VEVENT", "END:VCALENDAR"].filter(Boolean);
    window.location.href = "data:text/calendar;charset=utf-8," + encodeURIComponent(lines.join("\r\n"));
  };

  const field = { width: "100%", boxSizing: "border-box", background: "var(--glass)", color: "var(--fg)",
                  border: "1px solid var(--edge)", borderRadius: ".6rem", padding: ".55rem .7rem", font: "inherit", minWidth: 0 };
  const label = { display: "flex", flexDirection: "column", gap: ".3rem", fontSize: ".85rem", color: "var(--dim)", minWidth: 0 };
  const input = (key, kind, place) => (
    <input style={field} type={kind || "text"} value={form[key]} placeholder={place || ""}
           onInput={(e) => { setProblem(""); setForm({ ...form, [key]: e.currentTarget.value }); }} />
  );
  const host = (info && info.host) || text("book", "Book an appointment");
  const narrow = { maxWidth: "36rem" };
  const footer = info && info.email ? (
    <Text dim>{text("questions", "Questions or another moment?")} {info.email}</Text>
  ) : null;

  if (step === "done") {
    const b = booked;
    const gone = b && !b.error && b.status === "cancelled";
    return (
      <Screen title={host} subtitle={b && !b.error ? b.type : ""}>
        <div style={narrow}>
          <Card title={!b ? text("looking", "Looking up your booking...") : b.error ? text("notFound", "This booking cannot be found.")
            : gone ? text("cancelled", "This booking is cancelled.") : text("confirmed", "Your booking is confirmed.")}>
            {b && !b.error ? (
              <div>
                <Row left={text("when", "When")} right={`${dayLabel(b.starts)}, ${clock(b.starts)} - ${clock(b.ends)}`} />
                {b.place ? <Row left={text("where", "Where")} right={b.place} /> : null}
                {b.link && !gone ? <Row left={text("join", "Join")} right={b.link} /> : null}
              </div>
            ) : null}
            {b && !b.error && !gone ? (
              sure ? (
                <div>
                  <Text>{text("sure", "Cancel this booking?")}</Text>
                  <Buttons>
                    <Button primary onClick={() => { setSure(false); void view("cancel"); }}>{text("yesCancel", "Yes, cancel")}</Button>
                    <Button onClick={() => setSure(false)}>{text("keep", "No, keep it")}</Button>
                  </Buttons>
                </div>
              ) : (
                <Buttons>
                  {b.link ? <Button primary onClick={() => window.open(b.link, "_blank", "noopener")}>{text("openLink", "Open the video link")}</Button> : null}
                  <Button onClick={() => calendar(b)}>{text("addCalendar", "Add to my calendar")}</Button>
                  <Button onClick={() => setSure(true)}>{text("cancel", "Cancel the booking")}</Button>
                </Buttons>
              )
            ) : null}
            {b && !b.error && !gone ? <Text dim>{text("keepLink", "Keep this page's link: it is how you come back to your booking.")}</Text> : null}
            <Buttons><Button onClick={() => { window.location.href = window.location.pathname; }}>{text("another", "Book something else")}</Button></Buttons>
          </Card>
          {footer}
        </div>
      </Screen>
    );
  }

  if (step === "details") {
    return (
      <Screen title={host} subtitle={type.name}>
        <div style={narrow}>
          <Card title={text("yourBooking", "Your booking")}>
            <Row left={text("what", "What")} right={`${type.name}, ${type.minutes} min`} />
            <Row left={text("when", "When")} right={session ? `${dayLabel(session.starts)}, ${clock(session.starts)}` : `${dayLabel(day)}, ${slot}`} />
            <Row left={text("how", "How")} right={kindLabel(type)} />
          </Card>
          <Card title={text("details", "Your details")}>
            <div style={{ display: "flex", flexDirection: "column", gap: ".7rem" }}>
              <label style={label}>{text("name", "Name")}{input("name")}</label>
              <label style={label}>{text("email", "E-mail")}{input("email", "email", "name@example.com")}</label>
              <label style={label}>{text("note", "Anything to share beforehand? (optional)")}{input("note")}</label>
            </div>
          </Card>
          {problem ? <Text>{problem}</Text> : null}
          <Buttons>
            <Button primary onClick={() => confirm()}>{text("confirm", "Confirm the booking")}</Button>
            <Button onClick={() => setStep(type.kind === "webinar" ? "session" : "time")}>{text("back", "Back")}</Button>
          </Buttons>
        </div>
      </Screen>
    );
  }

  if (step === "session") {
    const list = type.sessions || [];
    return (
      <Screen title={host} subtitle={`${type.name}, ${type.minutes} min`}>
        <div style={narrow}>
          {type.text ? <Text dim>{type.text}</Text> : null}
          <Card title={text("sessions", "Pick a session")}>
            {!list.length ? <Text dim>{text("noSessions", "No sessions planned right now.")}</Text> : list.map((s) => (
              <div key={s.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: ".6rem",
                                       padding: ".45rem 0", borderTop: "1px solid var(--edge)", flexWrap: "wrap" }}>
                <span>{dayLabel(s.starts)}, {clock(s.starts)}
                  <span style={{ color: s.left ? "var(--dim)" : "var(--warn)", marginLeft: ".5rem", fontSize: ".85rem" }}>
                    {s.left ? text("seatsLeft", "{n} seats left").replace("{n}", s.left) : text("full", "This session is full.")}
                  </span>
                </span>
                {s.left ? <Button primary onClick={() => { setSession(s); setStep("details"); }}>{text("choose", "Choose")}</Button> : null}
              </div>
            ))}
          </Card>
          <Buttons><Button onClick={() => setStep("types")}>{text("back", "Back")}</Button></Buttons>
        </div>
      </Screen>
    );
  }

  if (step === "time") {
    const slots = (days.find((d) => d.day === day) || {}).slots || [];
    return (
      <Screen title={host} subtitle={`${type.name}, ${type.minutes} min`}>
        <div style={narrow}>
          {type.text ? <Text dim>{type.text}</Text> : null}
          <Card title={text("pickDay", "Pick a day")}>
            {!days.length ? <Text dim>{text("noTimes", "No free moments in the coming weeks.")}</Text> : (
              <Buttons>
                {days.slice(0, 14).map((d) => (
                  <Button key={d.day} primary={d.day === day} onClick={() => { setDay(d.day); setSlot(null); }}>{dayLabel(d.day)}</Button>
                ))}
              </Buttons>
            )}
          </Card>
          {day ? (
            <Card title={text("pickTime", "Pick a time")}>
              <Buttons>
                {slots.map((s) => <Button key={s} primary={s === slot} onClick={() => { setSlot(s); setStep("details"); }}>{s}</Button>)}
              </Buttons>
            </Card>
          ) : null}
          {problem ? <Text>{problem}</Text> : null}
          <Buttons><Button onClick={() => setStep("types")}>{text("back", "Back")}</Button></Buttons>
        </div>
      </Screen>
    );
  }

  return (
    <Screen title={host} subtitle={info && !info.open ? text("closedNow", "No bookings can be made right now.") : text("intro", "Pick what you would like to book.")}>
      <div style={narrow}>
        {problem ? <Text>{problem}</Text> : null}
        {info && !info.types.length ? <Text dim>{text("nothing", "Nothing to book yet.")}</Text> : null}
        {(info ? info.types : []).map((t) => (
          <Card key={t.id} title={t.name}>
            <Text dim>{`${t.minutes} min · ${kindLabel(t)}`}</Text>
            {t.text ? <Text>{t.text}</Text> : null}
            {info.open ? <Buttons><Button primary onClick={() => pick(t)}>{t.kind === "webinar" ? text("seeSessions", "See the sessions") : text("pickMoment", "Pick a moment")}</Button></Buttons> : null}
          </Card>
        ))}
        {footer}
      </div>
    </Screen>
  );
};
