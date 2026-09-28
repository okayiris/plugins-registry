export default () => {
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState("");
  const [system, setSystem] = useState("");

  const veld = {
    width: "100%", boxSizing: "border-box",
    background: "var(--glass)", color: "var(--fg)",
    border: "1px solid var(--edge)", borderRadius: 10,
    padding: "0.55rem 0.7rem", fontSize: "0.95rem",
    fontFamily: "inherit",
  };
  const label = {
    display: "flex", flexDirection: "column", gap: "0.3rem",
    fontSize: "0.85rem", color: "var(--dim)",
  };

  const klaar = prompt.trim().length > 0;
  const modelArg = model.trim() ? " --model " + model.trim() : "";
  const systemArg = system.trim() ? " --system " + JSON.stringify(system.trim()) : "";
  const vraag = "openrouter ask " + JSON.stringify(prompt.trim()) + modelArg + systemArg;
  const beeld = "openrouter image " + JSON.stringify(prompt.trim()) + modelArg;

  return (
    <div style={{display: "flex", flexDirection: "column", gap: "0.7rem", padding: "0.5rem", maxWidth: "min(92vw, 34rem)"}}>
      <Card label="OPENROUTER" title="Your account, your key">
        <Row left="Text" right="ask" />
        <Row left="Image" right="image, saved to your inbox" />
        <Row left="Video" right="when OpenRouter offers it" />
      </Card>

      <Text dim>Every call here is an explicit command and is paid from your own OpenRouter credit.</Text>

      <label style={label}>Prompt
        <textarea style={{...veld, minHeight: "4.5rem", resize: "vertical"}} value={prompt}
                  placeholder="What do you want to know, or what should be drawn?"
                  onInput={(e) => setPrompt(e.currentTarget.value)} />
      </label>

      <label style={label}>Model (optional)
        <input style={veld} type="text" value={model}
               placeholder="leave empty for the default"
               onInput={(e) => setModel(e.currentTarget.value)} />
      </label>

      <label style={label}>System (optional, text only)
        <input style={veld} type="text" value={system}
               placeholder="how the answer should behave"
               onInput={(e) => setSystem(e.currentTarget.value)} />
      </label>

      <div style={{display: "flex", gap: "0.6rem"}}>
        <Button primary uit={!klaar} say={vraag}>Ask</Button>
        <Button outline uit={!klaar} say={beeld}>Make image</Button>
      </div>

      <Text dim>{klaar ? (model.trim() ? "with " + model.trim() : "with your default model") : "Type a prompt first."}</Text>
    </div>
  );
};
