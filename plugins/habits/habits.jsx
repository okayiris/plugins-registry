export default () => (
  <Card label={text("label", "Habits")} title={text("title", "Your habits today")} icon="check">
    <Text dim>{text("intro", "Tell Iris when a habit is done; she keeps the streak.")}</Text>
    <Buttons>
      <Button primary say="habits">{text("today", "What is still open")}</Button>
      <Button say="habits week">{text("week", "The last seven days")}</Button>
      <Button say="habits streaks">{text("streaks", "My streaks")}</Button>
    </Buttons>
    <Text dim>{text("hint", "Say: I went for a walk, or: start a new habit, read.")}</Text>
  </Card>
);
