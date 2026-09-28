export default () => (
  <Card label={text("label", "Trains")} title={text("title", "Your trains")} icon="clock">
    <Text dim>{text("intro", "Live from the NS, with delays and track changes. The answer comes in the conversation.")}</Text>
    <Buttons>
      <Button primary say="trains">{text("departures", "Departures from home")}</Button>
      <Button say="trains work">{text("work", "To work")}</Button>
      <Button say="trains home">{text("home", "Back home")}</Button>
      <Button say="trains disruptions">{text("disruptions", "Disruptions")}</Button>
    </Buttons>
    <Text dim>{text("hint", "Say: when does the next train to Amsterdam leave?")}</Text>
  </Card>
);
