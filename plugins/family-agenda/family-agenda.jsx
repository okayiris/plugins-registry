export default () => {
  const vandaag = new Date().toISOString().slice(0, 10);
  const [datum, setDatum] = useState(vandaag);
  const [tijd, setTijd] = useState("16:00");
  const [wat, setWat] = useState("");
  const [wie, setWie] = useState("");
  const [waar, setWaar] = useState("");

  const veld = {
    width: "100%", boxSizing: "border-box",
    background: "var(--glass)", color: "var(--fg)",
    border: "1px solid var(--edge)", borderRadius: 10,
    padding: "0.55rem 0.7rem", fontSize: "0.95rem",
  };
  const label = {
    display: "flex", flexDirection: "column", gap: "0.3rem",
    fontSize: "0.85rem", color: "var(--dim)",
  };

  const klaar = wat.trim().length > 0;
  const boodschap = "family-agenda plan " + JSON.stringify(wat.trim()) + " " + datum + " " + tijd
    + (wie.trim() ? " --wie " + wie.trim() : "")
    + (waar.trim() ? " --waar " + waar.trim() : "");

  return (
    <div style={{display: "flex", flexDirection: "column", gap: "0.7rem", padding: "0.5rem", maxWidth: "min(92vw, 34rem)"}}>
      <div style={{fontWeight: 600, fontSize: "1.1rem"}}>{text("title", "Put something in the family agenda")}</div>

      <label style={label}>{text("what", "What")}
        <input style={veld} type="text" value={wat} placeholder={text("example", "e.g. dentist")}
               onInput={(e) => setWat(e.currentTarget.value)} />
      </label>

      <div style={{display: "flex", gap: "0.6rem"}}>
        <label style={{...label, flex: 1}}>{text("date", "Date")}
          <input style={veld} type="date" value={datum}
                 onInput={(e) => setDatum(e.currentTarget.value)} />
        </label>
        <label style={{...label, flex: 1}}>{text("time", "Time")}
          <input style={veld} type="time" value={tijd}
                 onInput={(e) => setTijd(e.currentTarget.value)} />
        </label>
      </div>

      <div style={{display: "flex", gap: "0.6rem"}}>
        <label style={{...label, flex: 1}}>{text("who", "Who (optional)")}
          <input style={veld} type="text" value={wie}
                 onInput={(e) => setWie(e.currentTarget.value)} />
        </label>
        <label style={{...label, flex: 1}}>{text("where", "Where (optional)")}
          <input style={veld} type="text" value={waar}
                 onInput={(e) => setWaar(e.currentTarget.value)} />
        </label>
      </div>

      <Knop primair uit={!klaar} onClick={() => nova(boodschap)}>{text("plan", "Put it in the agenda")}</Knop>

      <div style={{fontSize: "0.8rem", color: "var(--dim)"}}>
        {klaar ? boodschap : text("empty", "First fill in what is planned.")}
      </div>
    </div>
  );
};
