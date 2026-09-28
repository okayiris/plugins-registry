export default () => (
  <Card label={text("label", "Notes")} title={text("title", "Your notes")}>
    <Text dim>{text("intro", "Say what to remember and find it again later. Words like #work become tags.")}</Text>
    <Buttons>
      <Button primary say="notes">{text("latest", "The latest notes")}</Button>
      <Button say="notes tags">{text("tags", "My tags")}</Button>
    </Buttons>
    <Text dim>{text("hint", "Say: note that the plumber comes on Tuesday.")}</Text>
  </Card>
);
