export default () => {
  const startMinutes = 25;
  const startSeconds = startMinutes * 60;
  const [left, setLeft] = useState(startSeconds);
  const [total, setTotal] = useState(startSeconds);
  const [running, setRunning] = useState(false);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (!running || paused) return undefined;
    const id = setInterval(() => {
      setLeft((value) => (value > 0 ? value - 1 : 0));
    }, 1000);
    return () => clearInterval(id);
  }, [running, paused]);

  useEffect(() => {
    if (left === 0 && running) {
      setRunning(false);
      setPaused(false);
    }
  }, [left, running]);

  const minutes = Math.floor(left / 60);
  const seconds = left % 60;
  const clock = String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const progress = total > 0 ? left / total : 0;
  const offset = circumference * (1 - progress);
  const status = running
    ? (paused ? text("paused", "Paused") : text("running", "Running"))
    : text("idle", "Ready");

  const onStart = () => {
    if (left === 0) setLeft(total);
    setRunning(true);
    setPaused(false);
  };
  const onPause = () => {
    if (running) setPaused(true);
  };
  const onResume = () => {
    if (running) setPaused(false);
  };
  const onReset = () => {
    setRunning(false);
    setPaused(false);
    setLeft(total);
  };

  return (
    <Card label={text("label", "Focus")} title={text("title", "Focus timer")} icon="clock">
      <div style={{display: "flex", flexDirection: "column", alignItems: "center", gap: "0.8rem", padding: "0.4rem"}}>
        <div style={{position: "relative", width: "100%", maxWidth: "14rem", aspectRatio: "1 / 1"}}>
          <svg viewBox="0 0 120 120" width="100%" height="100%" role="img" aria-label={text("ring", "Time left")}>
            <circle cx="60" cy="60" r={radius} fill="none" stroke="var(--edge)" strokeWidth="8" />
            <circle cx="60" cy="60" r={radius} fill="none" stroke="var(--accent)" strokeWidth="8" strokeLinecap="round"
              strokeDasharray={circumference} strokeDashoffset={offset} transform="rotate(-90 60 60)" />
          </svg>
          <div style={{position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "0.15rem"}}>
            <div style={{fontSize: "clamp(1.8rem, 9vw, 3.2rem)", fontWeight: 600, color: "var(--fg)", fontVariantNumeric: "tabular-nums"}}>{clock}</div>
            <div style={{fontSize: "0.85rem", color: "var(--dim)"}}>{status}</div>
          </div>
        </div>
        <Buttons>
          <Button primary onClick={onStart}>{text("start", "Start")}</Button>
          <Button onClick={onPause}>{text("pause", "Pause")}</Button>
          <Button onClick={onResume}>{text("resume", "Resume")}</Button>
          <Button onClick={onReset}>{text("reset", "Reset")}</Button>
        </Buttons>
        <Text dim>{text("hint", "A block of 25 minutes. Pause when you need to, resume, or reset for a new block.")}</Text>
      </div>
    </Card>
  );
};
