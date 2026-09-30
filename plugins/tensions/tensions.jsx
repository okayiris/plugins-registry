// tensions - the widget: how many tensions are open, where they go (tactical or governance), which wait
// too long, and the heaviest few with the role they were sensed from. It asks its own command for the
// numbers each time it shows.

export default () => {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch("/commands/run", { method: "POST", body: JSON.stringify({ cmd: "tensions", args: "--json" }) });
        const d = await r.json();
        if (!d || !d.ok) throw new Error(d?.tekst || "the command failed");
        setData(JSON.parse(d.tekst));
      } catch (e) {
        setError(String(e?.message || e));
      }
    })();
  }, []);

  const label = text("label", "Tensions");
  if (!data) {
    return (
      <Card label={label} title={text("title", "Your tensions")} icon="chart">
        <Text dim>{error ? text("failed", "Could not load the tensions.") : text("loading", "Loading...")}</Text>
      </Card>
    );
  }

  const c = data.counts;
  const title = c.open === 0 ? text("none", "No open tensions")
    : c.open === 1 ? text("one", "1 open tension") : text("many", "{n} open tensions").replace("{n}", c.open);
  const kinds = { tactical: text("tactical", "Tactical"), governance: text("governance", "Governance"), "": text("untriaged", "Not triaged") };
  const ago = (n) => (n === 0 ? text("today", "today") : n === 1 ? text("yesterday", "yesterday") : text("daysAgo", "{n} days").replace("{n}", n));

  const dots = (w) => (
    <span style={{ display: "inline-flex", gap: ".18rem", flex: "none" }} title={text("weight", "Weight")}>
      {[1, 2, 3].map((i) => (
        <span key={i} style={{ width: ".45rem", height: ".45rem", borderRadius: "50%",
                               background: i <= w ? "var(--warn)" : "var(--edge)" }} />
      ))}
    </span>
  );

  return (
    <Card label={label} title={title} icon="chart">
      {c.open > 0 ? (
        <Stats>
          <Stat value={c.tactical} label={kinds.tactical} />
          <Stat value={c.governance} label={kinds.governance} />
          <Stat value={c.untriaged} label={kinds[""]} />
          <Stat value={c.stale} label={text("waiting", "Waiting long")} />
        </Stats>
      ) : (
        <Text dim>{text("calm", "Nothing is pulling right now. When something could be better, tell Iris from which role.")}</Text>
      )}

      {data.open.slice(0, 4).map((t) => (
        <div key={t.id} style={{ borderTop: "1px solid var(--edge)", padding: ".45rem 0", minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: ".5rem", minWidth: 0 }}>
            {dots(t.weight)}
            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }} title={t.text}>{t.text}</span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: ".2rem .6rem", fontSize: ".8rem", color: "var(--dim)", marginTop: ".15rem" }}>
            <span>{t.role || text("noRole", "No role")}</span>
            <span style={{ color: t.kind ? "var(--dim)" : "var(--faint)" }}>{kinds[t.kind] || kinds[""]}</span>
            {t.opportunity ? <span style={{ color: "var(--good)" }}>{text("opportunity", "Opportunity")}</span> : null}
            <span style={{ color: t.stale ? "var(--warn)" : "var(--faint)" }}>{ago(t.age)}</span>
          </div>
        </div>
      ))}
      {data.open.length > 4 ? (
        <Text dim>{text("more", "And {n} more.").replace("{n}", data.open.length - 4)}</Text>
      ) : null}

      <Buttons>
        <Button primary say={text("agendaSay", "What is on the agenda of the next tactical meeting?")}>{text("agenda", "Tactical agenda")}</Button>
        <Button say={text("governanceSay", "What is on the agenda of the next governance meeting?")}>{text("governanceAgenda", "Governance agenda")}</Button>
        <Button say={text("newSay", "I sense a tension.")}>{text("new", "New tension")}</Button>
      </Buttons>
    </Card>
  );
};
