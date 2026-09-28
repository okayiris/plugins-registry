const COLOURS = {
  werkt: "var(--accent)",
  working: "var(--accent)",
  wacht: "var(--warn)",
  waiting: "var(--warn)",
  klaar: "var(--good)",
  done: "var(--good)",
  fout: "var(--bad)",
  stuck: "var(--bad)",
};

const ORDER = { werkt: 0, working: 0, wacht: 1, waiting: 1, fout: 2, stuck: 2 };

function keyOf(status) {
  if (status === "working") return "werkt";
  if (status === "waiting") return "wacht";
  if (status === "done") return "klaar";
  if (status === "stuck") return "fout";
  return status;
}

function labelOf(status) {
  const key = keyOf(status);
  if (key === "werkt") return text("working", "Working");
  if (key === "wacht") return text("waiting", "Waiting");
  if (key === "klaar") return text("done", "Done");
  if (key === "fout") return text("stuck", "Stuck");
  return String(status || "");
}

function elapsed(sinds, now) {
  const start = Number(sinds);
  const total = Number.isFinite(start) ? Math.max(0, Math.floor(now - start)) : 0;
  return Math.floor(total / 60) + "m " + (total % 60) + "s";
}

export default () => {
  const [list, setList] = useState([]);
  const [quiet, setQuiet] = useState(false);
  const [now, setNow] = useState(() => Date.now() / 1000);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const response = await fetch("/klussen");
        const data = await response.json();
        if (alive) {
          setList(Array.isArray(data) ? data : []);
          setQuiet(false);
        }
      } catch (error) {
        if (alive) setQuiet(true);
      }
    }
    load();
    const poll = setInterval(load, 2000);
    return () => {
      alive = false;
      clearInterval(poll);
    };
  }, []);

  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(tick);
  }, []);

  const active = list
    .filter((item) => item && item.status !== "klaar" && item.status !== "done")
    .sort((a, b) => {
      const rankA = ORDER[a.status] === undefined ? 2 : ORDER[a.status];
      const rankB = ORDER[b.status] === undefined ? 2 : ORDER[b.status];
      if (rankA !== rankB) return rankA - rankB;
      return (Number(a.sinds) || 0) - (Number(b.sinds) || 0);
    });

  return (
    <div style={{ display: "grid", gap: "0.6rem", width: "100%", boxSizing: "border-box" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "0.6rem", flexWrap: "wrap" }}>
        <span style={{ fontSize: "clamp(1.3rem, 4vw, 2rem)", fontWeight: 600, color: "var(--fg)" }}>
          {text("title", "Workers")}
        </span>
        <span style={{ fontSize: "0.85rem", color: "var(--faint)" }}>
          {quiet ? text("noAnswer", "no answer") : active.length + " " + text("live", "live")}
        </span>
      </div>
      <div style={{ fontSize: "0.9rem", color: "var(--dim)" }}>
        {text("intro", "What this house is working on right now.")}
      </div>

      {active.length === 0 ? (
        <div style={{ fontSize: "0.95rem", color: "var(--dim)", padding: "0.6rem 0" }}>
          {text("none", "No worker is running right now.")}
        </div>
      ) : null}

      <div style={{ display: "grid", gap: "0.5rem" }}>
        {active.map((item, index) => {
          const colour = COLOURS[item.status] || "var(--dim)";
          const first = String(item.doe || "").split("\n")[0];
          return (
            <div
              key={index}
              style={{
                display: "grid",
                gridTemplateColumns: "10px 1fr auto",
                gap: "0.7rem",
                alignItems: "start",
                padding: "0.7rem 0.8rem",
                borderRadius: "12px",
                background: "var(--glass)",
                border: "1px solid var(--edge)",
                minWidth: 0,
              }}
            >
              <span style={{ width: "10px", height: "10px", borderRadius: "50%", marginTop: "0.35rem", background: colour }} />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: "1rem", color: "var(--fg)", overflowWrap: "anywhere" }}>{item.titel}</div>
                <div style={{ fontSize: "0.85rem", color: "var(--dim)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {first}
                </div>
              </div>
              <div style={{ textAlign: "right", fontSize: "0.8rem", color: "var(--dim)", whiteSpace: "nowrap" }}>
                {labelOf(item.status)}
                <br />
                {elapsed(item.sinds, now)}
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ fontSize: "0.8rem", color: "var(--faint)" }}>
        {text("keepsAnEye", "Talvi keeps an eye on these and picks up what is done.")}
      </div>
    </div>
  );
};
