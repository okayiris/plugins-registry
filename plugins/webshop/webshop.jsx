export default () => (
  <Card label={text("label", "Web shop")} title={text("title", "Your shop")}>
    <Text dim>{text("intro", "Add products by saying so; customers order on your own shop page.")}</Text>
    <Buttons>
      <Button primary say="webshop">{text("overview", "How is the shop doing")}</Button>
      <Button say="webshop orders">{text("orders", "Orders to handle")}</Button>
      <Button say="webshop products">{text("products", "Products and stock")}</Button>
      <Button say="webshop link">{text("link", "The shop's address")}</Button>
    </Buttons>
    <Text dim>{text("hint", "Say: put a mug in the shop for 12.50, there are 20.")}</Text>
  </Card>
);
