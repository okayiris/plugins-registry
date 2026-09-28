export default () => (
  <Card label={text("label", "Books")} title={text("title", "Your reading list")}>
    <Text dim>{text("intro", "Books to read, reading and read. Say a title and Iris finds it.")}</Text>
    <Buttons>
      <Button primary say="books">{text("now", "What am I reading")}</Button>
      <Button say="books list want">{text("want", "To read")}</Button>
      <Button say="books year">{text("year", "Read this year")}</Button>
    </Buttons>
    <Text dim>{text("hint", "Say: I want to read Project Hail Mary, or: I finished The Hobbit, four stars.")}</Text>
  </Card>
);
