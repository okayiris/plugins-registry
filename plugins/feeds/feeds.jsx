export default () => (
  <Card label={text("label", "Feeds")} title={text("title", "What is new")}>
    <Text dim>{text("intro", "The news and blogs you follow, newest first. The answer comes in the conversation.")}</Text>
    <Buttons>
      <Button primary say="feeds">{text("latest", "The newest")}</Button>
      <Button say="feeds list">{text("list", "What I follow")}</Button>
      <Button say="feeds refresh">{text("refresh", "Read them again")}</Button>
    </Buttons>
    <Text dim>{text("add", "Follow a site by saying: follow the feed of, with its name and address.")}</Text>
  </Card>
);
