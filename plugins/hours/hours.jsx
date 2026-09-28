// Hours: the timer, the week per day and per project, and the entries, with hours to add afterwards.
// The screen asks its own command for JSON through /commands/run (hours data <week> --json), and every
// change goes through the same command, so what Iris says and what the screen shows are the same hours.

export default () => {
  const [data, setData] = useState(null);
  const [loadedAt, setLoadedAt] = useState(Date.now());
  const [, setTick] = useState(0);
  const [offset, setOffset] = useState(0);
  const [problem, setProblem] = useState("");
  const [said, setSaid] = useState("");
  const [note, setNote] = useState("");
  const [form, setForm] = useState({ project: "", hours: "", day: "", note: "" });
  const [fresh, setFresh] = useState(null);
  const [sure, setSure] = useState(null);

  const run = async (args) => {
    let d;
    try {
      const r = await fetch("/commands/run", { method: "POST", body: JSON.stringify({ cmd: "hours", args }) });
      d = await r.json();
    } catch (e) {
      throw new Error(text("noBridge", "This screen cannot reach your hours here. Ask Iris instead."));
    }
    const body = String(d?.tekst ?? d?.text ?? d?.output ?? "");
    if (!d || !d.ok) throw new Error(body.trim() || text("failed", "That did not work. Try again in a moment."));
    return body;
  };

  const load = async (week = offset) => {
    try {
      const got = JSON.parse(await run(`data ${week} --json`));
      setData(got);
      setLoadedAt(Date.now());
      setForm((f) => ({ ...f, day: f.day || got.today, project: f.project || (got.projects[0] ? String(got.projects[0].id) : "") }));
    } catch (e) {
      setProblem(String(e?.message || e));
    }
  };

  const act = async (args, after, done) => {
    setProblem("");
    setSaid("");
    try {
      await run(args);
      setSaid(done || "");
      if (after) after();
      await load();
      return true;
    } catch (e) {
      setProblem(String(e?.message || e));
      return false;
    }
  };

  useEffect(() => { void load(); }, []);
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const quote = (s) => `"${String(s).replace(/["\\]/g, "").trim()}"`;
  const hm = (m) => `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
  const lang = document.documentElement.lang || undefined;
  const money = (c) => {
    try {
      return new Intl.NumberFormat(lang, { style: "currency", currency: (data && data.currency) || "EUR" }).format(c / 100);
    } catch (e) {
      return (c / 100).toFixed(2);
    }
  };
  const dayLabel = (iso, long) => {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(lang, long ? { weekday: "long", day: "numeric", month: "long" }
      : { weekday: "short", day: "numeric", month: "short" });
  };

  const field = { width: "100%", boxSizing: "border-box", background: "var(--glass)", color: "var(--fg)",
                  border: "1px solid var(--edge)", borderRadius: ".6rem", padding: ".5rem .65rem", font: "inherit", minWidth: 0 };
  const label = { display: "flex", flexDirection: "column", gap: ".3rem", fontSize: ".85rem", color: "var(--dim)", minWidth: 0 };
  const grid = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))", gap: ".7rem" };
  const line = { display: "flex", alignItems: "center", justifyContent: "space-between", gap: ".6rem",
                 padding: ".45rem 0", borderTop: "1px solid var(--edge)", flexWrap: "wrap" };

  if (!data) {
    return (
      <Screen title={text("title", "Hours")}>
        <Text dim>{problem || text("loading", "Your hours are on their way...")}</Text>
      </Screen>
    );
  }

  const week = data.week;
  const r = data.running;
  // The house's clock at loading plus the time since: the timer counts on without asking again.
  const nowMs = Date.parse(data.now) + (Date.now() - loadedAt);
  const runSeconds = r ? Math.max(0, Math.floor((nowMs - Date.parse(r.starts)) / 1000)) : 0;
  const runClock = `${Math.floor(runSeconds / 3600)}:${String(Math.floor(runSeconds / 60) % 60).padStart(2, "0")}:${String(runSeconds % 60).padStart(2, "0")}`;
  const weekTitle = offset === 0 ? text("thisWeek", "This week") : offset === -1 ? text("lastWeek", "Last week")
    : text("weekNumber", "Week {n}").replace("{n}", week.number);
  const byDay = {};
  for (const e of data.entries) (byDay[e.day] = byDay[e.day] || []).push(e);

  const add = () => {
    if (!form.hours.trim()) { setProblem(text("needHours", "Say how long: like 2,5 or 1:30 or 09:00-12:30.")); return; }
    if (!form.project) { setProblem(text("needProject", "Pick a project, or make a new one first.")); return; }
    const where = form.project === "new" ? quote(fresh && fresh.name ? fresh.name : "") : `#${form.project}`;
    if (form.project === "new" && !(fresh && fresh.name && fresh.name.trim())) {
      setProblem(text("needName", "Give the new project a name."));
      return;
    }
    void act(`add ${quote(form.hours.replace(/\s/g, ""))} ${where} ${form.day || data.today}${form.note.trim() ? ` ${quote(form.note)}` : ""}`,
      () => { setForm({ ...form, hours: "", note: "", project: form.project === "new" ? "" : form.project }); setFresh(null); },
      text("added", "Added."));
  };

  return (
    <Screen title={text("title", "Hours")} subtitle={`${weekTitle}: ${dayLabel(week.start)} - ${dayLabel(week.end)}`}>
      <Card label={text("timer", "Timer")} title={r ? r.project : text("noTimer", "No timer running")}>
        {r ? (
          <div>
            <div style={{ fontSize: "2.4rem", fontWeight: 600, fontVariantNumeric: "tabular-nums", color: "var(--accent)" }}>{runClock}</div>
            <Text dim>{text("since", "Since {t}").replace("{t}", r.starts.slice(11, 16))}{r.note ? ` · ${r.note}` : ""}</Text>
            <Buttons>
              <Button primary onClick={() => act("stop", null, text("stopped", "The timer is stopped."))}>{text("stop", "Stop")}</Button>
              <Button onClick={() => setSure(`timer`)}>{text("discard", "Throw away")}</Button>
            </Buttons>
            {sure === "timer" ? (
              <Buttons>
                <Text>{text("sureTimer", "Throw this timer away, without keeping its time?")}</Text>
                <Button primary onClick={() => { setSure(null); void act(`remove ${r.id}`, null, text("discarded", "The timer is thrown away.")); }}>{text("yesDiscard", "Yes, throw away")}</Button>
                <Button onClick={() => setSure(null)}>{text("no", "No")}</Button>
              </Buttons>
            ) : null}
          </div>
        ) : (
          <div>
            <label style={label}>{text("doing", "What are you working on? (optional)")}
              <input style={field} value={note} onInput={(e) => setNote(e.currentTarget.value)} />
            </label>
            {data.projects.length ? (
              <Buttons>
                {data.projects.slice(0, 6).map((p, i) => (
                  <Button key={p.id} primary={i === 0} onClick={() => act(`start #${p.id}${note.trim() ? ` ${quote(note)}` : ""}`, () => setNote(""))}>
                    {text("startOn", "Start {p}").replace("{p}", p.name)}
                  </Button>
                ))}
              </Buttons>
            ) : <Text dim>{text("firstProject", "Add your first hours below, with a new project.")}</Text>}
          </div>
        )}
      </Card>

      {problem ? <Text>{problem}</Text> : said ? <Text dim>{said}</Text> : null}

      <Stats>
        <Stat label={text("today", "Today")} value={hm(data.todayMinutes)} />
        <Stat label={data.target ? text("ofTarget", "{w}, of {t}").replace("{w}", weekTitle).replace("{t}", hm(data.target)) : weekTitle}
              value={hm(week.total)} />
        <Stat label={text("billable", "Billable, {h}").replace("{h}", hm(week.billable))} value={money(week.amount)} />
      </Stats>

      <Card title={text("addHours", "Add hours")}>
        <div style={grid}>
          <label style={label}>{text("project", "Project")}
            <select style={field} value={form.project} onChange={(e) => { setProblem(""); setForm({ ...form, project: e.currentTarget.value }); }}>
              {data.projects.map((p) => <option key={p.id} value={String(p.id)}>{p.name}{p.client ? ` (${p.client})` : ""}</option>)}
              <option value="new">{text("newProject", "New project...")}</option>
            </select>
          </label>
          {form.project === "new" || !data.projects.length ? (
            <label style={label}>{text("projectName", "Name of the new project")}
              <input style={field} value={(fresh && fresh.name) || ""} placeholder={text("projectExample", "Website Bakker")}
                     onInput={(e) => { setProblem(""); setFresh({ name: e.currentTarget.value }); if (form.project !== "new") setForm({ ...form, project: "new" }); }} />
            </label>
          ) : null}
          <label style={label}>{text("howLong", "How long")}
            <input style={field} value={form.hours} placeholder="2,5 / 1:30 / 09:00-12:30"
                   onInput={(e) => { setProblem(""); setForm({ ...form, hours: e.currentTarget.value }); }} />
          </label>
          <label style={label}>{text("day", "Day")}
            <input style={field} type="date" value={form.day} max={data.today}
                   onInput={(e) => { setProblem(""); setForm({ ...form, day: e.currentTarget.value }); }} />
          </label>
        </div>
        <label style={{ ...label, marginTop: ".7rem" }}>{text("note", "What you did (optional)")}
          <input style={field} value={form.note} onInput={(e) => setForm({ ...form, note: e.currentTarget.value })} />
        </label>
        <Buttons><Button primary onClick={() => add()}>{text("add", "Add")}</Button></Buttons>
      </Card>

      <Card title={weekTitle}>
        <Buttons>
          <Button onClick={() => { setOffset(offset - 1); void load(offset - 1); }}>{text("earlier", "Week before")}</Button>
          {offset < 0 ? <Button onClick={() => { setOffset(offset + 1); void load(offset + 1); }}>{text("later", "Week after")}</Button> : null}
          {offset < -1 ? <Button onClick={() => { setOffset(0); void load(0); }}>{text("thisWeek", "This week")}</Button> : null}
        </Buttons>
        {week.days.map((d) => (
          <Row key={d.day} left={dayLabel(d.day, true)} right={d.minutes ? hm(d.minutes) : "-"} />
        ))}
        <Row left={text("total", "Together")} right={hm(week.total)} />
      </Card>

      <Card title={text("perProject", "Per project")}>
        {!week.projects.length ? <Text dim>{text("noHours", "No hours in this week.")}</Text> : week.projects.map((p) => (
          <Row key={p.id} left={p.client ? `${p.name} (${p.client})` : p.name}
               right={p.amount ? `${hm(p.minutes)} · ${money(p.amount)}` : hm(p.minutes)} />
        ))}
      </Card>

      <Card title={text("entries", "Entries")}>
        {!data.entries.length ? <Text dim>{text("noHours", "No hours in this week.")}</Text> : Object.keys(byDay).map((day) => (
          <div key={day}>
            <div style={{ color: "var(--dim)", fontSize: ".8rem", marginTop: ".6rem" }}>{dayLabel(day, true)}</div>
            {byDay[day].map((e) => (
              <div key={e.id} style={line}>
                <span style={{ minWidth: 0, overflowWrap: "anywhere" }}>
                  <b>{hm(e.minutes)}</b> {e.project}
                  {e.starts && e.ends ? <span style={{ color: "var(--dim)" }}> · {e.starts.slice(11, 16)}-{e.ends.slice(11, 16)}</span> : null}
                  {e.note ? <span style={{ color: "var(--dim)" }}> · {e.note}</span> : null}
                  {e.running ? <span style={{ color: "var(--accent)" }}> · {text("running", "running")}</span> : null}
                  {!e.billable ? <span style={{ color: "var(--faint)" }}> · {text("notBillable", "not billable")}</span> : null}
                  {e.invoiced ? <span style={{ color: "var(--good)" }}> · {text("invoiced", "invoiced")}</span> : null}
                </span>
                {e.invoiced || e.running ? null : sure === e.id ? (
                  <Buttons>
                    <Button primary onClick={() => { setSure(null); void act(`remove ${e.id}`, null, text("removed", "Removed.")); }}>{text("yesRemove", "Yes, remove")}</Button>
                    <Button onClick={() => setSure(null)}>{text("no", "No")}</Button>
                  </Buttons>
                ) : <Button onClick={() => setSure(e.id)}>{text("remove", "Remove")}</Button>}
              </div>
            ))}
          </div>
        ))}
        <Buttons>
          <Button say={`hours export ${offset === 0 ? "week" : offset === -1 ? "last week" : week.start.slice(0, 7)}`}>{text("export", "Export as CSV")}</Button>
          <Button say="hours month">{text("month", "This month")}</Button>
        </Buttons>
      </Card>
    </Screen>
  );
};
