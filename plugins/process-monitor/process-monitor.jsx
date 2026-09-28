// process-monitor - Process Monitor: live view of what runs inside this house: every
// process with its user, cpu, memory and age, the workbench boxes that are busy right
// now, and a stop button that first asks, then stops. The floor (pid 1, the desktop,
// the assistant, the watchers) is protected and shows why instead of a button.
//
// A screen lives in the talk page, so it can fetch: it asks its own command for the
// same JSON with /commands/run. Stopping goes through the same command with --ja,
// only after a second, deliberate tap here.

export default () => {
  const [beeld, setBeeld] = useState(null);
  const [fout, setFout] = useState("");
  const [melding, setMelding] = useState("");
  const [bezig, setBezig] = useState(0);
  const [bevestig, setBevestig] = useState(0);
  const [zombies, setZombies] = useState(false);

  const laad = async () => {
    try {
      const r = await fetch("/commands/run", {
        method: "POST",
        body: JSON.stringify({ cmd: "processes", args: "--json" }),
      });
      const d = await r.json();
      if (!d || !d.ok) throw new Error(d?.tekst || "the command failed");
      setBeeld(JSON.parse(d.tekst));
      setFout("");
    } catch (e) {
      setFout(String(e?.message || e));
    }
  };

  useEffect(() => {
    void laad();
    const t = setInterval(() => void laad(), 4000);
    return () => clearInterval(t);
  }, []);

  const stop = async (pid) => {
    setBezig(pid);
    setMelding("");
    try {
      const r = await fetch("/commands/run", {
        method: "POST",
        body: JSON.stringify({ cmd: "processes", args: `stop ${pid} --ja` }),
      });
      const d = await r.json();
      if (!d || !d.ok) throw new Error(d?.tekst || "stopping failed");
      setBevestig(0);
      setMelding(d.tekst);
      setTimeout(() => void laad(), 500);
    } catch (e) {
      setFout(String(e?.message || e));
    } finally {
      setBezig(0);
    }
  };

  const mb = (x) => (x >= 1024 ? `${(x / 1024).toFixed(1)} GB` : `${x} MB`);

  const kleinKnop = (extra) => ({
    display: "inline-flex", alignItems: "center", gap: ".3rem",
    background: extra?.primair ? "var(--accent)" : "var(--glass)",
    color: extra?.primair ? "#07090c" : "var(--fg)",
    border: "1px solid var(--edge)", borderRadius: ".5rem",
    padding: ".3rem .55rem", font: "inherit", fontSize: ".78rem",
    fontWeight: 600, cursor: "pointer",
  });

  if (!beeld) {
    return (
      <Scherm titel="Process Monitor" sub="what runs inside this house" icoon="meter">
        {fout ? <Tekst dim>Could not load the list: {fout}</Tekst> : <Tekst dim>Loading…</Tekst>}
        <Knoppen>
          <Knop icoon="vernieuw" onClick={() => void laad()}>Refresh</Knop>
          <Knop icoon="kruis" onClick={() => dicht()}>Close</Knop>
        </Knoppen>
      </Scherm>
    );
  }

  const alle = beeld.procs || [];
  const levend = alle.filter((p) => !p.zombie);
  const zicht = alle.filter((p) => zombies || !p.zombie);
  const beschermd = levend.filter((p) => p.beschermd).length;
  const geheugen = Math.round(levend.reduce((som, p) => som + p.mb, 0));
  const boxen = beeld.boxen || [];
  const dienst = beeld.dienst || {};

  const procesRij = (p) => (
    <div key={p.pid} style={{ borderTop: "1px solid var(--edge)", padding: ".55rem 0" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: ".6rem" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: ".4rem", minWidth: 0 }}>
          <Icoon naam={p.beschermd ? "schild" : "hartslag"} maat={14} />
          <b style={{ fontWeight: 600 }}>{p.naam}</b>
          <span className="mono" style={{ color: "var(--faint)" }}>{p.pid}</span>
          {p.zombie ? <span style={{ color: "var(--faint)", fontSize: ".75rem" }}>zombie</span> : null}
        </span>
        <span style={{ color: "var(--dim)", whiteSpace: "nowrap", fontSize: ".84rem" }}>
          {p.cpu}% · {mb(p.mb)} · {p.sinds_tekst}
        </span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: ".6rem", marginTop: ".2rem",
                    color: "var(--dim)", fontSize: ".84rem" }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              title={p.commando}>{p.commando}</span>
        <span style={{ color: "var(--faint)", flex: "none" }}>{p.gebruiker}</span>
      </div>
      <div style={{ marginTop: ".35rem", display: "flex", alignItems: "center", gap: ".5rem", flexWrap: "wrap" }}>
        {p.zombie ? (
          <span style={{ color: "var(--faint)", fontSize: ".78rem" }}>already gone</span>
        ) : p.beschermd ? (
          <span style={{ color: "var(--faint)", fontSize: ".78rem" }}>protected: {p.reden}</span>
        ) : bevestig === p.pid ? (
          <>
            <span style={{ color: "var(--dim)", fontSize: ".8rem" }}>Are you sure?</span>
            <button type="button" style={kleinKnop({ primair: true })} disabled={bezig === p.pid}
                    onClick={() => void stop(p.pid)}>
              <Icoon naam="stop" maat={12} /> Yes, stop
            </button>
            <button type="button" style={kleinKnop()} onClick={() => setBevestig(0)}>
              <Icoon naam="kruis" maat={12} /> No
            </button>
          </>
        ) : (
          <button type="button" style={kleinKnop()} onClick={() => setBevestig(p.pid)}>
            <Icoon naam="stop" maat={12} /> Stop
          </button>
        )}
      </div>
    </div>
  );

  return (
    <Scherm titel="Process Monitor" sub="what runs inside this house" icoon="meter">
      <Stats>
        <Stat waarde={levend.length} label="processes" icoon="server" />
        <Stat waarde={beschermd} label="protected" icoon="schild" />
        <Stat waarde={mb(geheugen)} label="memory" icoon="database" />
        <Stat waarde={boxen.length} label="workbenches busy" icoon="pakket" />
      </Stats>

      {fout ? <Tekst dim>Could not load the list: {fout}</Tekst> : null}
      {melding ? <Tekst dim>{melding}</Tekst> : null}

      <Kaart label="WORKBENCHES" icoon="pakket">
        {!dienst.bereikbaar ? (
          <Tekst dim>Workbench service not reachable; this house may not have one.</Tekst>
        ) : null}
        {boxen.length === 0 ? (
          <Tekst dim>No workbench boxes running right now.</Tekst>
        ) : boxen.map((b) => (
          <div key={b.pid} style={{ borderTop: "1px solid var(--edge)", padding: ".5rem 0" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: ".6rem" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: ".4rem" }}>
                <Icoon naam="pakket" maat={14} />
                <b style={{ fontWeight: 600 }}>{b.map}</b>
              </span>
              <span style={{ color: "var(--dim)", whiteSpace: "nowrap", fontSize: ".84rem" }}>
                {b.leeftijd_tekst} · {b.status}
              </span>
            </div>
            <div style={{ color: "var(--dim)", fontSize: ".84rem", marginTop: ".2rem",
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  title={b.commando}>{b.commando || "no command"}</div>
          </div>
        ))}
      </Kaart>

      <Kaart label="PROCESSES" icoon="server">
        {zicht.map(procesRij)}
        <div style={{ borderTop: "1px solid var(--edge)", paddingTop: ".5rem", marginTop: ".2rem" }}>
          <button type="button" style={kleinKnop()} onClick={() => setZombies(!zombies)}>
            {zombies ? "Hide zombies" : `Show zombies (${alle.length - levend.length})`}
          </button>
        </div>
      </Kaart>

      <Knoppen>
        <Knop icoon="vernieuw" onClick={() => void laad()}>Refresh</Knop>
        <Knop icoon="kruis" onClick={() => dicht()}>Close</Knop>
      </Knoppen>
    </Scherm>
  );
};
