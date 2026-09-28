export default () => {
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [from, setFrom] = useState("");

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

  const klaar = to.trim().length > 0 && subject.trim().length > 0 && body.trim().length > 0;
  const q = (s) => JSON.stringify(s);
  const sendCmd = "maillog send --to " + q(to.trim())
    + " --subject " + q(subject.trim())
    + " --body " + q(body.trim())
    + (from.trim() ? " --from " + q(from.trim()) : "");

  return (
    <div style={{display: "flex", flexDirection: "column", gap: "0.7rem",
                 padding: "0.5rem", maxWidth: "min(92vw, 36rem)"}}>
      <div style={{fontWeight: 600, fontSize: "1.1rem"}}>Maillog</div>

      <Card title="Send mail" icon="mail">
        <div style={{display: "flex", flexDirection: "column", gap: "0.6rem", paddingTop: "0.4rem"}}>
          <label style={label}>To
            <input style={veld} type="email" value={to} placeholder="name@example.com"
                   onInput={(e) => setTo(e.currentTarget.value)} />
          </label>
          <label style={label}>Subject
            <input style={veld} type="text" value={subject}
                   onInput={(e) => setSubject(e.currentTarget.value)} />
          </label>
          <label style={label}>From (optional)
            <input style={veld} type="text" value={from} placeholder="verified@your-domain"
                   onInput={(e) => setFrom(e.currentTarget.value)} />
          </label>
          <label style={label}>Body
            <textarea style={{...veld, minHeight: "6rem", resize: "vertical"}} value={body}
                      onInput={(e) => setBody(e.currentTarget.value)} />
          </label>
          <Button primary uit={!klaar} onClick={() => klaar && nova(sendCmd)}>Review the message</Button>
          <Text dim>The command shows the message once more; it only goes out after you confirm it.</Text>
        </div>
      </Card>

      <Card title="Read what Maillog did" icon="chart">
        <div style={{display: "flex", flexDirection: "column", gap: "0.5rem", paddingTop: "0.4rem"}}>
          <Row left="Events" right="recent mail and delivery" />
          <Row left="Stats" right="daily numbers" />
          <Row left="Logs" right="every API call" />
          <Button onClick={() => nova("maillog events --limit 10")}>Recent messages</Button>
          <Button onClick={() => nova("maillog stats --days 7")}>Last 7 days</Button>
          <Button onClick={() => nova("maillog logs --limit 10")}>API log</Button>
        </div>
      </Card>

      <Card title="How it works">
        <List items={[
          "Send mail through your own Maillog account.",
          "Read the send log, delivery status and daily numbers.",
          "The key stays in the vault; this tool never sees it.",
          "Mail only leaves after you confirm the exact message.",
        ]} />
      </Card>
    </div>
  );
};
