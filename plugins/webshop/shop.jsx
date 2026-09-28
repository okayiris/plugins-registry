// The shop page on the house's own address (/shop): the products, a cart, the checkout and, after paying,
// how the order stands. It talks only to its own command through pageApi; it shows no customer data but
// the visitor's own order, and that only with the order's own token from the link Mollie sends back to.

export default () => {
  const params = new URLSearchParams(window.location.search);
  const [shop, setShop] = useState(null);
  const [products, setProducts] = useState([]);
  const [cart, setCart] = useState({});
  const [step, setStep] = useState(params.get("order") ? "done" : "shop");
  const [form, setForm] = useState({ name: "", email: "", phone: "", address: "", note: "", delivery: "pickup" });
  const [problem, setProblem] = useState("");
  const [result, setResult] = useState(null);
  const [broken, setBroken] = useState({});

  const euro = (c) => {
    try {
      return new Intl.NumberFormat(document.documentElement.lang || undefined, { style: "currency", currency: (shop && shop.currency) || "EUR" }).format(c / 100);
    } catch (e) {
      return `${(c / 100).toFixed(2)}`;
    }
  };

  const load = async () => {
    const data = await pageApi({ action: "catalog" });
    if (data && data.shop) {
      setShop(data.shop);
      setProducts(data.products || []);
      if (!data.shop.pickup) setForm((f) => ({ ...f, delivery: "ship" }));
    } else {
      setProblem(text("unavailable", "The shop cannot be reached right now. Try again in a moment."));
    }
  };

  const status = async () => {
    const data = await pageApi({ action: "status", order: params.get("order"), token: params.get("token") });
    setResult(data && !data.error ? data : { error: true });
  };

  useEffect(() => {
    void load();
    if (params.get("order")) void status();
  }, []);

  const count = Object.values(cart).reduce((a, b) => a + b, 0);
  const lines = products.filter((p) => cart[p.id]).map((p) => ({ ...p, qty: cart[p.id] }));
  const subtotal = lines.reduce((a, l) => a + l.price * l.qty, 0);
  const shipping = form.delivery === "ship" && shop
    ? (shop.free_from != null && subtotal >= shop.free_from ? 0 : shop.shipping) : 0;

  const add = (p, n) => {
    const now = cart[p.id] || 0;
    const next = Math.max(0, Math.min(now + n, p.left == null ? 99 : p.left));
    const copy = { ...cart };
    if (next) copy[p.id] = next; else delete copy[p.id];
    setCart(copy);
  };

  const order = async () => {
    setProblem("");
    const data = await pageApi({
      action: "order",
      items: lines.map((l) => ({ id: l.id, qty: l.qty })),
      customer: form,
    });
    if (!data || data.error) {
      const why = {
        customer: text("needName", "Fill in your name and a valid e-mail address."),
        address: text("needAddress", "Fill in the address to send it to."),
        stock: text("stock", "Not enough of one product is left; the cart shows what is still there."),
        gone: text("gone", "One product is no longer in the shop."),
        closed: text("closed", "The shop takes no orders right now."),
        empty: text("empty", "Your cart is empty."),
      }[data && data.error] || text("failed", "Ordering did not work. Try again in a moment.");
      setProblem(why);
      if (data && (data.error === "stock" || data.error === "gone")) void load();
      return;
    }
    if (data.pay) {
      window.location.href = data.pay;
      return;
    }
    setResult(data);
    setCart({});
    setStep("done");
  };

  const field = { width: "100%", boxSizing: "border-box", background: "var(--glass)", color: "var(--fg)",
                  border: "1px solid var(--edge)", borderRadius: ".6rem", padding: ".55rem .7rem", font: "inherit", minWidth: 0 };
  const label = { display: "flex", flexDirection: "column", gap: ".3rem", fontSize: ".85rem", color: "var(--dim)", minWidth: 0 };
  const input = (key, type, place) => (
    <input style={field} type={type || "text"} value={form[key]} placeholder={place || ""}
           onInput={(e) => setForm({ ...form, [key]: e.currentTarget.value })} />
  );

  const photo = (p) => (p.photo && !broken[p.id] ? (
    <img src={p.photo} alt={p.name} loading="lazy" onError={() => setBroken({ ...broken, [p.id]: true })}
         style={{ width: "100%", aspectRatio: "4 / 3", objectFit: "cover", display: "block" }} />
  ) : (
    <div style={{ width: "100%", aspectRatio: "4 / 3", display: "flex", alignItems: "center", justifyContent: "center",
                  background: "var(--glass)", color: "var(--faint)" }}>
      <Icon name="pakket" size={32} />
    </div>
  ));

  const footer = shop ? (
    <div style={{ marginTop: "1.5rem", paddingTop: ".8rem", borderTop: "1px solid var(--edge)", color: "var(--dim)", fontSize: ".82rem" }}>
      <div>{[shop.name, shop.address, shop.kvk ? `KvK ${shop.kvk}` : "", shop.email].filter(Boolean).join(" · ")}</div>
      {shop.terms ? <div style={{ marginTop: ".4rem", whiteSpace: "pre-line" }}>{shop.terms}</div> : null}
    </div>
  ) : null;

  if (step === "done") {
    const state = result && !result.error ? result.status : null;
    const title = !result ? text("checking", "Looking up your order...")
      : result.error ? text("notFound", "This order cannot be found.")
      : state === "paid" || state === "shipped" ? text("thanksPaid", "Thank you, your payment has come in.")
      : state === "cancelled" ? text("cancelled", "This order was cancelled; nothing was paid.")
      : shop && shop.payments === "mollie" && result.pay ? text("waitingPay", "Your order is waiting for payment.")
      : text("thanks", "Thank you for your order.");
    return (
      <Screen title={(shop && shop.name) || text("shop", "Shop")} subtitle={result && result.order ? `${text("order", "Order")} #${result.order}` : ""}>
        <Card title={title}>
          {result && result.lines ? result.lines.map((l, i) => (
            <Row key={i} left={`${l.qty} x ${l.name}`} right={euro(l.price * l.qty)} />
          )) : null}
          {result && result.shipping ? <Row left={text("shipping", "Shipping")} right={euro(result.shipping)} /> : null}
          {result && result.total != null ? <Row left={text("total", "Total")} right={euro(result.total)} /> : null}
          {result && !result.error && state === "open" && !result.pay ? (
            <Text dim>{text("requestNext", "You will receive a payment request by e-mail. Once it is paid, your order is sent or ready to pick up.")}</Text>
          ) : null}
          <Buttons>
            {result && result.pay ? <Button primary onClick={() => { window.location.href = result.pay; }}>{text("payNow", "Pay now")}</Button> : null}
            <Button onClick={() => { window.location.href = window.location.pathname; }}>{text("back", "Back to the shop")}</Button>
          </Buttons>
        </Card>
        {footer}
      </Screen>
    );
  }

  if (step === "checkout") {
    return (
      <Screen title={(shop && shop.name) || text("shop", "Shop")} subtitle={text("checkout", "Check out")}>
        <div style={{ maxWidth: "34rem" }}>
          <Card title={text("yourOrder", "Your order")}>
            {lines.map((l) => <Row key={l.id} left={`${l.qty} x ${l.name}`} right={euro(l.price * l.qty)} />)}
            {shipping ? <Row left={text("shipping", "Shipping")} right={euro(shipping)} /> : null}
            <Row left={text("total", "Total")} right={euro(subtotal + shipping)} />
          </Card>
          <Card title={text("details", "Your details")}>
            <div style={{ display: "flex", flexDirection: "column", gap: ".7rem" }}>
              <label style={label}>{text("name", "Name")}{input("name", "text")}</label>
              <label style={label}>{text("email", "E-mail")}{input("email", "email", "name@example.com")}</label>
              <label style={label}>{text("phone", "Phone (optional)")}{input("phone", "tel")}</label>
              {shop && shop.pickup ? (
                <Buttons>
                  <Button primary={form.delivery === "pickup"} onClick={() => setForm({ ...form, delivery: "pickup" })}>{text("pickup", "Pick it up")}</Button>
                  <Button primary={form.delivery === "ship"} onClick={() => setForm({ ...form, delivery: "ship" })}>
                    {text("ship", "Send it")}{shop.shipping ? ` (+${euro(shop.shipping)})` : ""}
                  </Button>
                </Buttons>
              ) : null}
              {form.delivery === "ship" ? <label style={label}>{text("address", "Address")}{input("address", "text", text("addressHint", "Street and number, postcode, town"))}</label> : null}
              <label style={label}>{text("note", "A note (optional)")}{input("note", "text")}</label>
            </div>
          </Card>
          {problem ? <Text>{problem}</Text> : null}
          <Buttons>
            <Button primary onClick={() => order()}>
              {shop && shop.payments === "mollie" ? text("orderPay", "Order and pay") : text("orderSend", "Place the order")}
            </Button>
            <Button onClick={() => setStep("shop")}>{text("back", "Back to the shop")}</Button>
          </Buttons>
          {shop && shop.payments === "mollie" ? <Text dim>{text("payNote", "You pay safely at Mollie, with iDEAL or a card.")}</Text> : null}
        </div>
        {footer}
      </Screen>
    );
  }

  return (
    <Screen title={(shop && shop.name) || text("shop", "Shop")}
            subtitle={shop && !shop.open ? text("closedNow", "The shop is closed right now; you can look around.") : ""}>
      {problem ? <Text>{problem}</Text> : null}
      {shop && !products.length ? <Text dim>{text("noProducts", "Nothing in the shop yet. Come back soon.")}</Text> : null}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(12rem, 1fr))", gap: ".9rem" }}>
        {products.map((p) => (
          <div key={p.id} style={{ display: "flex", flexDirection: "column", border: "1px solid var(--edge)", borderRadius: ".9rem",
                                   overflow: "hidden", background: "var(--glass)", minWidth: 0 }}>
            {photo(p)}
            <div style={{ padding: ".7rem .8rem .8rem", display: "flex", flexDirection: "column", gap: ".35rem", flex: 1 }}>
              <b style={{ fontWeight: 600 }}>{p.name}</b>
              {p.text ? <span style={{ color: "var(--dim)", fontSize: ".86rem" }}>{p.text}</span> : null}
              <b style={{ fontWeight: 700 }}>{euro(p.price)}</b>
              {p.sold_out ? <span style={{ color: "var(--warn)", fontSize: ".82rem" }}>{text("soldOut", "Sold out")}</span>
                : p.left != null && p.left <= 3 ? <span style={{ color: "var(--dim)", fontSize: ".82rem" }}>{text("left", "Only {n} left").replace("{n}", p.left)}</span> : null}
              <div style={{ marginTop: "auto" }}>
                {p.sold_out ? null : cart[p.id] ? (
                  <Buttons>
                    <Button onClick={() => add(p, -1)}>-</Button>
                    <span style={{ minWidth: "1.5rem", textAlign: "center" }}>{cart[p.id]}</span>
                    <Button onClick={() => add(p, 1)}>+</Button>
                  </Buttons>
                ) : (
                  <Buttons><Button primary onClick={() => add(p, 1)}>{text("add", "Add to cart")}</Button></Buttons>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
      {count ? (
        <Card title={`${text("cart", "Cart")}: ${count} · ${euro(subtotal)}`}>
          <Buttons>
            <Button primary onClick={() => { if (shop && shop.open) setStep("checkout"); else setProblem(text("closed", "The shop takes no orders right now.")); }}>
              {text("toCheckout", "Check out")}
            </Button>
            <Button onClick={() => setCart({})}>{text("clear", "Empty the cart")}</Button>
          </Buttons>
        </Card>
      ) : null}
      {footer}
    </Screen>
  );
};
