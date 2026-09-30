export default () => {
  const [data, setData] = useState(null);
  const [loadedAt, setLoadedAt] = useState(0);
  const [tick, setTick] = useState(0);
  const [view, setView] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  const two = (n) => String(n).padStart(2, "0");
  const hour = (s) => String(s || "").slice(11, 16);
  const quote = (s) => "\"" + String(s || "").replace(/"/g, "'").replace(/\s+/g, " ").trim() + "\"";

  // The window asks its own command, like the house's own screens do (/commands/run).
  const run = async (args) => {
    const r = await fetch("/commands/run", { method: "POST", body: JSON.stringify({ cmd: "planner", args: args + " --json" }) });
    const d = await r.json();
    const body = d && (d.tekst ?? d.text ?? d.output);
    let out;
    try { out = JSON.parse(body); } catch (e) { throw new Error(body || text("noAnswer", "The planner did not answer.")); }
    if (out && out.error) throw new Error(out.error);
    return out;
  };

  const load = async () => {
    setError("");
    try {
      const out = await run("today");
      setData(out);
      setLoadedAt(Date.now());
    } catch (e) {
      setError(String((e && e.message) || e));
    }
  };

  useEffect(() => { void load(); }, []);
  // The clock moves on by itself, so the next appointment takes over the moment one ends.
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30000);
    return () => clearInterval(id);
  }, []);

  const act = async (args, message) => {
    setError("");
    setDone("");
    try {
      const out = await run(args);
      await load();
      setDone(message(out));
    } catch (e) {
      setError(String((e && e.message) || e));
    }
  };

  const frame = (children) => (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem", padding: "0.5rem", maxWidth: "min(94vw, 38rem)" }}>
      {children}
    </div>
  );
  const note = (error || done) ? <Text dim>{error ? text("failed", "That did not work") + ": " + error : done}</Text> : null;

  if (!data) {
    return frame(
      <Card label={text("label", "Plan assistant")} title={text("title", "Your day")} icon="calendar">
        <Text dim>{error ? text("failed", "That did not work") + ": " + error : text("loading", "Reading your day...")}</Text>
      </Card>
    );
  }

  // The server's clock, moved on by the time this window has been open.
  const serverNow = new Date(data.now.replace(" ", "T"));
  const now = new Date(serverNow.getTime() + (loadedAt ? Date.now() - loadedAt : 0));
  const nowText = data.day + " " + two(now.getHours()) + ":" + two(now.getMinutes());
  const evening = view ? view === "evening" : now.getHours() >= 17;

  const entries = data.timeline.filter((x) => x.kind === "entry" && !x.allday);
  const mineOnly = entries.filter((x) => x.who === "me" || x.who === "family" || x.who === "?");
  const current = mineOnly.find((x) => x.start <= nowText && nowText < x.end);
  const next = mineOnly.find((x) => x.start > nowText);
  const leave = next ? data.timeline.find((x) => x.kind === "leave" && x.title === next.title) : null;
  const prepFor = next ? data.prep.find((p) => p.key === next.key) : null;

  const taskRow = (t) => (
    <div key={t.id} style={{ display: "grid", gap: "0.25rem", paddingTop: "0.3rem" }}>
      <Row left={t.title} right={t.promised ? text("promised", "promised") : ""} />
      <Buttons>
        <Button outline onClick={() => act("done " + t.id, () => text("didIt", "Done") + ": " + t.title)}>{text("done", "Done")}</Button>
        {evening ? [
          <Button outline key="t" onClick={() => act("move " + t.id + " tomorrow", () => t.title + ": " + text("toTomorrow", "tomorrow"))}>{text("tomorrow", "Tomorrow")}</Button>,
          <Button outline key="o" onClick={() => act("move " + t.id + " overmorrow", () => t.title + ": " + text("toOvermorrow", "the day after"))}>{text("overmorrow", "Day after")}</Button>,
          <Button outline key="w" onClick={() => act("move " + t.id + " nextweek", () => t.title + ": " + text("toNextWeek", "next week"))}>{text("nextWeek", "Next week")}</Button>,
          <Button outline key="l" onClick={() => act("move " + t.id + " later", () => t.title + ": " + text("toLater", "later"))}>{text("later", "Later")}</Button>,
        ] : null}
      </Buttons>
    </div>
  );

  const header = (
    <Card label={text("label", "Plan assistant")} title={data.label} icon="calendar">
      {current ? <Row left={text("now", "Now")} right={current.title + ", " + text("until", "until") + " " + hour(current.end)} /> : null}
      {next ? (
        <div style={{ display: "grid", gap: "0.3rem" }}>
          <Text>{text("nextIs", "This is your next appointment")}</Text>
          <Row left={hour(next.start)} right={next.title + (next.place ? ", " + next.place : "")} />
          {leave ? <Row left={text("leaveAt", "Leave at") + " " + hour(leave.start)}
            right={leave.minutes + " " + text("min", "min") + (leave.traffic ? ", " + text("traffic", "with traffic") : "")} /> : null}
          {prepFor ? <Text dim>{text("firstFinish", "Finish first") + ": " + prepFor.tasks.map((t) => t.title).join(", ")}</Text> : null}
          {next.place ? (
            <Buttons>
              <Button outline say={"Where can I park and get something to eat or drink near " + next.title + "? (planner near " + next.ref + ")"}>
                {text("near", "Parking and food there")}
              </Button>
            </Buttons>
          ) : null}
        </div>
      ) : <Text dim>{text("nothingNext", "Nothing more planned today.")}</Text>}
      <Buttons>
        <Button primary={!evening} outline={evening} onClick={() => setView("day")}>{text("today", "Today")}</Button>
        <Button primary={evening} outline={!evening} onClick={() => setView("evening")}>{text("evening", "Evening")}</Button>
      </Buttons>
      {note}
    </Card>
  );

  const promised = data.promised.length ? (
    <Card label={text("promisedLabel", "Promised")} title={data.setLastNight ? text("promisedLastNight", "You set these last night") : text("promisedTitle", "First thing today")} icon="clock">
      {data.promised.map(taskRow)}
    </Card>
  ) : null;

  const lineOf = (x) => {
    if (x.kind === "leave") return <Row key={"l" + x.start + x.title} left={hour(x.start)} right={text("leaveFor", "Leave for") + " " + x.title + " (" + x.minutes + " " + text("min", "min") + ")"} />;
    if (x.kind === "block") return <Row key={"b" + x.start + x.title} left={hour(x.start) + " - " + hour(x.end)} right={x.block === "meal" ? text(x.title.toLowerCase(), x.title) : text("pause", "Break")} />;
    const isNow = current && current.key === x.key;
    const who = x.who && x.who !== "me" && x.who !== "?"
      ? " (" + (x.source === "ride" ? x.who + " " + text("drives", "drives") : x.who) + ")" : "";
    return <Row key={x.key} left={x.allday ? text("allDay", "all day") : (isNow ? text("nowShort", "now") + " " : "") + hour(x.start) + " - " + hour(x.end)}
      right={x.title + who + (x.place && x.source !== "ride" ? ", " + x.place : "")} />;
  };

  const timeline = (
    <Card label={text("dayLabel", "The day")} title={text("timeline", "Timeline")} icon="calendar">
      {data.timeline.length ? data.timeline.map(lineOf) : <Text dim>{text("empty", "Nothing planned. Meals and breaks appear once there is something.")}</Text>}
    </Card>
  );

  const alerts = data.clashes.length || data.warnings.length || data.questions.length || data.review.length ? (
    <Card label={text("attention", "Attention")} title={text("attentionTitle", "Worth a look")}>
      {data.clashes.map((c, i) => <Text key={"c" + i}>{text("clash", "Clash") + ": " + c.a + " / " + c.b + ", " + c.from + " - " + c.until + (c.who !== "me" ? " (" + c.who + ")" : "")}</Text>)}
      {data.warnings.map((w, i) => <Text dim key={"w" + i}>{w}</Text>)}
      {data.questions.map((q) => (
        <Buttons key={"q" + q.calendar}>
          <Button outline say={"Whose calendar is " + q.calendar + "? Ask me once and remember it (planner owner)."}>
            {text("whose", "Whose calendar is") + " " + q.calendar + "?"}
          </Button>
        </Buttons>
      ))}
      {data.review.map((e) => (
        <Buttons key={"r" + e.key}>
          <Button outline say={"Ask me how " + e.title + " went, and keep it (planner review " + e.ref + ")."}>
            {text("howWas", "How was") + " " + e.title + "?"}
          </Button>
        </Buttons>
      ))}
    </Card>
  ) : null;

  const todoist = data.todoist || [];
  const tasks = data.tasks.length || data.prep.length || todoist.length ? (
    <Card label={text("tasksLabel", "Tasks")} title={evening ? text("leftOpen", "What is left open") : text("tasksTitle", "To do today")}>
      {data.prep.map((p) => (
        <div key={p.key} style={{ display: "grid", gap: "0.2rem", paddingTop: "0.3rem" }}>
          <Text dim>{text("before", "Before") + " " + p.title + " (" + p.at + ")"}</Text>
          {p.tasks.map(taskRow)}
        </div>
      ))}
      {data.tasks.map(taskRow)}
      {todoist.length ? <Text dim>{text("inTodoist", "In Todoist")}</Text> : null}
      {todoist.map((t) => (
        <div key={"td" + t.id} style={{ display: "grid", gap: "0.25rem", paddingTop: "0.3rem" }}>
          <Row left={t.content} right={t.when || ""} />
          <Buttons>
            <Button outline say={"Tick off " + t.content + " in Todoist (todoist done " + t.n + ")."}>{text("done", "Done")}</Button>
          </Buttons>
        </div>
      ))}
    </Card>
  ) : null;

  const recap = (
    <Card label={text("recapLabel", "Looking back")} title={text("recapTitle", "What you did today")} icon="clock">
      <Stats>
        <Stat value={entries.filter((x) => x.end <= nowText && x.source !== "ride").length} label={text("statMeetings", "appointments")} />
        <Stat value={data.done.length} label={text("statDone", "tasks done")} />
        <Stat value={data.tasks.length + data.promised.length} label={text("statOpen", "still open")} />
      </Stats>
      {data.done.map((t) => <Row key={"d" + t.id} left={t.title} right={text("doneShort", "done")} />)}
      <Buttons>
        <Button primary say="Look ahead at tomorrow with me (planner tomorrow).">{text("lookAhead", "Look ahead at tomorrow")}</Button>
      </Buttons>
    </Card>
  );

  return frame(evening
    ? [header, recap, tasks, promised, alerts].filter(Boolean)
    : [header, promised, alerts, timeline, tasks].filter(Boolean));
};
