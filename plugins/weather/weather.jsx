export default () => (
  <Card label={text("label", "Weather")} title={text("title", "The weather at home")}>
    <Text dim>{text("intro", "Ask for now, the week or rain, here or anywhere. The answer comes in the conversation.")}</Text>
    <Buttons>
      <Button primary say="weather">{text("now", "Now and the next hours")}</Button>
      <Button say="weather rain">{text("rain", "Will it rain soon")}</Button>
      <Button say="weather week">{text("week", "The week ahead")}</Button>
    </Buttons>
    <Text dim>{text("home", "Set your home under Integrations, or say: my home is Utrecht.")}</Text>
  </Card>
);
