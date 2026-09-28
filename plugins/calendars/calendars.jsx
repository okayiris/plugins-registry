export default () => (
  <Card label={text("label", "Calendars")} title={text("title", "All your calendars together")} icon="calendar">
    <Text dim>{text("text", "The calendars you added under Integrations, in one agenda. Ask for a day, and the answer comes in the conversation.")}</Text>
    <Buttons>
      <Button primary say="calendars week">{text("week", "The week ahead")}</Button>
      <Button say="calendars">{text("today", "Today and tomorrow")}</Button>
    </Buttons>
    <Text dim>{text("add", "A calendar joins by its link: say add my calendar, with a name and the .ics address.")}</Text>
  </Card>
);
