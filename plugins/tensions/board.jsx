// tensions - the board: every open tension per role, heaviest first, with what is needed next. A tension
// that is not triaged gets Tactical and Governance; every open one can be processed with the outcome
// Holacracy knows (a next action, a project, a new role...). It all goes through the plugin's own command.

export default () => {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [closing, setClosing] = useState(0);

  const run = async (args) => {
    const r = await fetch("/commands/run", { method: "POST", body: JSON.stringify({ cmd: "tensions", args }) });
    const d = await r.json();
    if (!d || !d.ok) throw new Error(d?.tekst || "the command failed");
    return d.tekst;
  };

  const load = async () => {
    try {
      setData(JSON.parse(await run("--json")));
      setError("");
    } catch (e) {
      setError(String(e?.message || e));
    }
  };

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 60000);
    return () => clearInterval(t);
  }, []);

  const act = async (args) => {
    try {
      await run(args);
      setClosing(0);
      await load();
    } catch (e) {
      setError(String(e?.message || e));
    }
  };

  const kinds = { tactical: text("tactical", "Tactical"), governance: text("governance", "Governance"), "": text("untriaged", "Not triaged") };
  const outcomes = {
    "next-action": text("outNextAction", "Next action"), project: text("outProject", "Project"),
    information: text("outInformation", "Information"), help: text("outHelp", "Help"),
    role: text("outRole", "Role change"), policy: text("outPolicy", "Policy"), election: text("outElection", "Election"),
    dropped: text("outDropped", "Dropped"),
  };
  const tacticalOut = ["next-action", "project", "information", "help"];
  const governanceOut = ["role", "policy", "election"];
  const ago = (n) => (n === 0 ? text("today", "today") : n === 1 ? text("yesterday", "yesterday") : text("daysAgo", "{n} days").replace("{n}", n));

  const title = text("screenTitle", "Tensions");
  const sub = text("screenSub", "The gap between how things are and how they could be, per role");

  if (!data) {
    return (
      <Screen title={title} subtitle={sub} icon="chart">
        <Text dim>{error ? text("failed", "Could not load the tensions.") : text("loading", "Loading...")}</Text>
        <Buttons><Button onClick={() => dicht()}>{text("close", "Close")}</Button></Buttons>
      </Screen>
    );
  }

  const c = data.counts;
  const filters = [
    ["all", text("all", "All"), c.open], ["tactical", kinds.tactical, c.tactical], ["governance", kinds.governance, c.governance],
    ["untriaged", kinds[""], c.untriaged], ["opportunity", text("opportunities", "Opportunities"), c.opportunities],
  ];
  const shown = data.open.filter((t) => filter === "all" ? true : filter === "untriaged" ? !t.kind
    : filter === "opportunity" ? t.opportunity : t.kind === filter);
  const roles = [];
  for (const t of shown) {
    let g = roles.find((r) => r.role === t.role);
    if (!g) roles.push(g = { role: t.role, items: [] });
    g.items.push(t);
  }
  roles.sort((a, b) => b.items.length - a.items.length || a.role.localeCompare(b.role));
  const quiet = data.roles.filter((r) => r.open === 0).map((r) => r.role);

  const dots = (w) => (
    <span style={{ display: "inline-flex", gap: ".2rem", flex: "none", paddingTop: ".45rem" }} title={text("weight", "Weight")}>
      {[1, 2, 3].map((i) => (
        <span key={i} style={{ width: ".5rem", height: ".5rem", borderRadius: "50%",
                               background: i <= w ? "var(--warn)" : "var(--edge)" }} />
      ))}
    </span>
  );

  const tension = (t) => (
    <div key={t.id} style={{ borderTop: "1px solid var(--edge)", padding: ".6rem 0", display: "flex", gap: ".7rem", minWidth: 0 }}>
      {dots(t.weight)}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ overflowWrap: "anywhere" }}>{t.text}</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: ".2rem .7rem", fontSize: ".8rem", color: "var(--dim)", marginTop: ".2rem" }}>
          <span className="mono" style={{ color: "var(--faint)" }}>{t.id}</span>
          <span style={{ color: t.kind ? "var(--dim)" : "var(--faint)" }}>{kinds[t.kind] || kinds[""]}</span>
          {t.circle ? <span>{t.circle}</span> : null}
          {t.opportunity ? <span style={{ color: "var(--good)" }}>{text("opportunity", "Opportunity")}</span> : null}
          <span style={{ color: t.stale ? "var(--warn)" : "var(--faint)" }}>
            {t.stale ? text("waitingFor", "waiting {n}").replace("{n}", ago(t.age)) : ago(t.age)}
          </span>
        </div>
        {closing === t.id ? (
          <div style={{ marginTop: ".3rem" }}>
            <Text dim>{text("how", "How was it processed?")}</Text>
            <Buttons>
              {(t.kind === "tactical" ? tacticalOut : t.kind === "governance" ? governanceOut : tacticalOut.concat(governanceOut))
                .concat(["dropped"]).map((o) => (
                  <Button key={o} onClick={() => act(`process ${t.id} ${o}`)}>{outcomes[o]}</Button>
                ))}
              <Button onClick={() => setClosing(0)}>{text("cancel", "Cancel")}</Button>
            </Buttons>
          </div>
        ) : (
          <Buttons>
            {!t.kind ? <Button onClick={() => act(`triage ${t.id} tactical`)}>{kinds.tactical}</Button> : null}
            {!t.kind ? <Button onClick={() => act(`triage ${t.id} governance`)}>{kinds.governance}</Button> : null}
            <Button onClick={() => setClosing(t.id)}>{text("processed", "Processed")}</Button>
          </Buttons>
        )}
      </div>
    </div>
  );

  return (
    <Screen title={title} subtitle={sub} icon="chart">
      <Stats>
        <Stat value={c.open} label={text("open", "Open")} />
        <Stat value={c.tactical} label={kinds.tactical} />
        <Stat value={c.governance} label={kinds.governance} />
        <Stat value={c.untriaged} label={kinds[""]} />
        <Stat value={c.stale} label={text("waitingDays", "Waiting over {n} days").replace("{n}", data.stale_days)} />
        <Stat value={c.processed_week} label={text("week", "Processed this week")} />
      </Stats>

      {error ? <Text dim>{text("failed", "Could not load the tensions.")}</Text> : null}

      <Buttons>
        {filters.map(([key, name, n]) => (
          <Button key={key} primary={filter === key} onClick={() => setFilter(key)}>{`${name} ${n}`}</Button>
        ))}
      </Buttons>

      {c.open === 0 ? (
        <Card label={text("label", "Tensions")} title={text("none", "No open tensions")}>
          <Text dim>{text("calm", "Nothing is pulling right now. When something could be better, tell Iris from which role.")}</Text>
        </Card>
      ) : shown.length === 0 ? (
        <Text dim>{text("nothingHere", "No open tensions here.")}</Text>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 22rem), 1fr))", gap: "0 .9rem" }}>
          {roles.map((g) => (
            <Card key={g.role} label={g.role || text("noRole", "No role")}
                  title={g.items.length === 1 ? text("one", "1 open tension") : text("many", "{n} open tensions").replace("{n}", g.items.length)}>
              {g.items.map(tension)}
            </Card>
          ))}
        </div>
      )}

      {quiet.length ? <Text dim>{text("quiet", "No open tensions in: {roles}.").replace("{roles}", quiet.join(", "))}</Text> : null}

      {data.recent.length ? (
        <Card label={text("recent", "Recently processed")}>
          {data.recent.map((t) => (
            <Row key={t.id} left={t.text} right={`${outcomes[t.outcome] || t.outcome} · ${t.role}`} />
          ))}
        </Card>
      ) : null}

      <Buttons>
        <Button primary say={text("newSay", "I sense a tension.")}>{text("new", "New tension")}</Button>
        <Button say={text("agendaSay", "What is on the agenda of the next tactical meeting?")}>{text("agenda", "Tactical agenda")}</Button>
        <Button onClick={() => dicht()}>{text("close", "Close")}</Button>
      </Buttons>
    </Screen>
  );
};
