export default () => (
  <Card label={text("label", "Stripe")} title={text("title", "Read-only overview")} icon="card">
    <Text dim>{text("intro", "Your own Stripe data with a restricted key that only reads. Nothing here creates, changes or refunds anything.")}</Text>
    <Stats>
      <Stat value="1.0.0" label={text("version", "read-only")} />
      <Stat value="GET" label={text("requests", "requests")} />
    </Stats>
    <Row left={text("rowBalance", "Balance and revenue")} right={text("readRight", "read")} />
    <Row left={text("rowPayments", "Payments and customers")} right={text("readRight", "read")} />
    <Row left={text("rowInvoices", "Invoices and subscriptions")} right={text("readRight", "read")} />
    <List items={[
      "stripe balance",
      "stripe payments --limit 10",
      "stripe customers --search <term>",
      "stripe invoices --status open",
      "stripe subscriptions --status active",
      "stripe revenue --month YYYY-MM",
    ]} />
    <Buttons>
      <Button primary say="stripe balance">{text("seeBalance", "Balance")}</Button>
      <Button say="stripe revenue">{text("seeRevenue", "Revenue this month")}</Button>
      <Button say="stripe payments --limit 10">{text("seePayments", "Latest payments")}</Button>
      <Button say="stripe customers">{text("seeCustomers", "Customers")}</Button>
      <Button say="stripe invoices --status open">{text("seeInvoices", "Open invoices")}</Button>
      <Button say="stripe subscriptions --status active">{text("seeSubs", "Active subscriptions")}</Button>
    </Buttons>
    <Text dim>{text("hint", "The answer appears in the conversation. Connect a restricted read-only key with: stripe key ask.")}</Text>
  </Card>
);
