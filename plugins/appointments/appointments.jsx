export default () => (
  <Card label={text("label", "Appointments")} title={text("title", "Your bookings")}>
    <Text dim>{text("windowIntro", "People book time with you on your own booking page.")}</Text>
    <Buttons>
      <Button primary say="appointments list today">{text("today", "Today")}</Button>
      <Button say="appointments list">{text("week", "The coming week")}</Button>
      <Button say="appointments types">{text("types", "Appointment types")}</Button>
      <Button say="appointments link">{text("link", "The booking page's address")}</Button>
    </Buttons>
    <Text dim>{text("hint", "Say: I am not available on Friday afternoon.")}</Text>
  </Card>
);
