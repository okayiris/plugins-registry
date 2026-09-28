export default () => (
  <Card label={text("label", "Checklists")} title={text("title", "Your lists")}>
    <Text dim>{text("intro", "Lists you use again and again. Say what is done; Iris ticks it off.")}</Text>
    <Buttons>
      <Button primary say="checklists">{text("all", "All my lists")}</Button>
      <Button say={text("packSay", "Show my packing list")}>{text("pack", "Packing list")}</Button>
    </Buttons>
    <Text dim>{text("hint", "Say: make a packing list with passport, charger and sunscreen.")}</Text>
  </Card>
);
