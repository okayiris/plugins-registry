export default () => (
  <Card label={text("label", "Expenses")} title={text("title", "What you spend")} icon="euro">
    <Text dim>{text("intro", "Say what you paid and for what; Iris adds it up per month and category.")}</Text>
    <Buttons>
      <Button primary say="expenses">{text("month", "This month")}</Button>
      <Button say="expenses month">{text("compare", "Compared with last month")}</Button>
      <Button say="expenses budget">{text("budgets", "My budgets")}</Button>
    </Buttons>
    <Text dim>{text("hint", "Say: I spent 42 euro on groceries.")}</Text>
  </Card>
);
