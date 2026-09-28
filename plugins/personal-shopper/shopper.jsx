// Personal shopper: the results of the last search from every shop side by side, a cart per shop,
// the kept products and the orders. The screen asks its own command for JSON through /commands/run;
// ordering always takes a second, deliberate tap, and paying happens on each shop's own page.

export default () => {
  const [view, setView] = useState("results");
  const [results, setResults] = useState({ query: "", items: [], problems: [] });
  const [cart, setCart] = useState({ shops: [], count: 0 });
  const [saved, setSaved] = useState([]);
  const [orders, setOrders] = useState([]);
  const [shop, setShop] = useState("");
  const [sort, setSort] = useState("best");
  const [stockOnly, setStockOnly] = useState(false);
  const [choose, setChoose] = useState(null);
  const [confirm, setConfirm] = useState(false);
  const [ordered, setOrdered] = useState(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [broken, setBroken] = useState({});

  // /commands/run is how the house's own screens reach their command (process-monitor does the same).
  // Where it is missing or answers differently, the screen says so and hands the question to Iris.
  const [bridge, setBridge] = useState(true);
  const run = async (args) => {
    let d;
    try {
      const r = await fetch("/commands/run", {
        method: "POST",
        body: JSON.stringify({ cmd: "shopper", args: `${args} --json` }),
      });
      d = await r.json();
    } catch (e) {
      setBridge(false);
      throw new Error(text("noBridge", "This screen cannot reach the shopper here. Ask Iris instead."));
    }
    const body = d?.tekst ?? d?.text ?? d?.output;
    if (!d || !d.ok) throw new Error(body || text("failed", "The shopper did not answer."));
    let data;
    try {
      data = JSON.parse(body);
    } catch (e) {
      setBridge(false);
      throw new Error(text("noBridge", "This screen cannot reach the shopper here. Ask Iris instead."));
    }
    if (data.error) throw new Error(data.error);
    return data;
  };

  const act = async (args, after) => {
    setError("");
    try {
      const data = await run(args);
      if (after) after(data);
      return data;
    } catch (e) {
      setError(String(e?.message || e));
      return null;
    }
  };

  const loadAll = () => {
    void act("results", setResults);
    void act("cart", setCart);
  };

  useEffect(() => { loadAll(); }, []);
  useEffect(() => {
    if (view === "saved") void act("saved", (d) => setSaved(d.saved || []));
    if (view === "orders") void act("orders", (d) => setOrders(d.orders || []));
  }, [view]);

  const price = (cents, cur) => {
    if (cents === null || cents === undefined) return text("unknown", "price unknown");
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency: cur || "EUR" }).format(cents / 100);
    } catch (e) {
      return `${(cents / 100).toFixed(2)} ${cur || ""}`;
    }
  };

  const why = (p) => typeof p === "string" ? p : `${p.shop} (${{
    no_search: text("whyNoSearch", "no open search, add its products by link"),
    not_selling: text("whyNotSelling", "sells nothing through its web shop"),
    down: text("whyDown", "did not answer"),
  }[p.why] || p.why})`;

  const how = (o) => ({
    filled: text("howFilled", "Opens the shop's own checkout with everything already in it."),
    cart: text("howCart", "Puts it in the shop's cart."),
    steps: text("howSteps", "Open each product to put it in the shop's cart, then pay."),
    page: text("howPage", "This shop has no cart link; order it on the product page."),
  }[o.code] || o.how);

  const picture = (src, alt, style, key) => (src && !broken[key] ? (
    <img src={src} alt={alt} loading="lazy" style={style}
         onError={() => setBroken((b) => ({ ...b, [key]: true }))} />
  ) : (
    <div style={{ ...style, display: "flex", alignItems: "center", justifyContent: "center",
                  color: "var(--faint)", background: "var(--glass)" }}>
      <Icon name="pakket" size={24} />
    </div>
  ));

  const totals = (shops) => {
    const by = {};
    shops.forEach((s) => { by[s.currency || ""] = (by[s.currency || ""] || 0) + s.total; });
    return Object.entries(by).map(([cur, c]) => price(c, cur)).join(" + ") || "-";
  };

  const add = async (n, variantId) => {
    const data = await act(`add ${n}${variantId ? ` --variant ${variantId}` : ""}`);
    if (!data) return;
    if (data.need === "variant") {
      setChoose({ n, variants: data.variants || [], options: data.options || [] });
      return;
    }
    setChoose(null);
    if (data.cart) setCart(data.cart);
    setNote(text("added", "In the cart."));
  };

  const keepIt = (n) => act(`save ${n}`, () => setNote(text("kept", "Kept to decide later.")));
  const setQty = (line, qty) => act(`qty ${line} ${qty}`, (d) => d.cart && setCart(d.cart));
  const order = () => act("order --yes", (d) => {
    setOrdered(d.ordered || []);
    setConfirm(false);
    setNote("");
    setCart({ shops: [], count: 0 });
  });
  const open = (url) => window.open(url, "_blank", "noopener");

  // --- the results -------------------------------------------------------------------------------

  const items = (results.items || []).map((it, i) => ({ ...it, n: i + 1 }));
  const shopNames = [...new Set(items.map((it) => it.shop))];
  let shown = items.filter((it) => (!shop || it.shop === shop) && (!stockOnly || it.available));
  if (sort === "low") shown = [...shown].sort((a, b) => (a.price ?? 1e12) - (b.price ?? 1e12));
  if (sort === "high") shown = [...shown].sort((a, b) => (b.price ?? -1) - (a.price ?? -1));

  const tile = (it) => (
    <div key={it.n} style={{ display: "flex", flexDirection: "column", border: "1px solid var(--edge)",
                             borderRadius: ".8rem", overflow: "hidden", background: "var(--glass)", minWidth: 0 }}>
      {picture(it.image, it.title, { width: "100%", aspectRatio: "1 / 1", objectFit: "cover", display: "block" }, `r${it.n}`)}
      <div style={{ padding: ".6rem .7rem .7rem", display: "flex", flexDirection: "column", gap: ".3rem", flex: 1 }}>
        <span style={{ color: "var(--dim)", fontSize: ".78rem" }}>{it.shop}{it.brand && it.brand !== it.shop ? `, ${it.brand}` : ""}</span>
        <b style={{ fontWeight: 600, lineHeight: 1.25, display: "-webkit-box", WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical", overflow: "hidden" }} title={it.title}>{it.title}</b>
        <span>
          <b style={{ fontWeight: 700 }}>{price(it.price, it.currency)}</b>
          {it.was ? <span style={{ color: "var(--faint)", textDecoration: "line-through", marginLeft: ".4rem",
                                   fontSize: ".85rem" }}>{price(it.was, it.currency)}</span> : null}
        </span>
        {it.available ? null : <span style={{ color: "var(--warn)", fontSize: ".8rem" }}>{text("soldOut", "Sold out")}</span>}
        <div style={{ marginTop: "auto" }}>
          {choose && choose.n === it.n ? (
            <div>
              <Text dim>{choose.options.join(", ") || text("which", "Which one?")}</Text>
              <Buttons>
                {choose.variants.filter((v) => v.available).map((v) => (
                  <Button key={v.id} onClick={() => add(it.n, v.id)}>{v.title}</Button>
                ))}
                <Button onClick={() => setChoose(null)}>{text("cancel", "Cancel")}</Button>
              </Buttons>
            </div>
          ) : (
            <Buttons>
              {it.available ? <Button primary onClick={() => add(it.n)}>{text("add", "Add")}</Button> : null}
              <Button onClick={() => keepIt(it.n)}>{text("keep", "Keep")}</Button>
              <Button onClick={() => open(it.url)}>{text("view", "View")}</Button>
            </Buttons>
          )}
        </div>
      </div>
    </div>
  );

  const resultsView = () => {
    if (!items.length) {
      return (
        <Card label={text("start", "Start shopping")} icon="chart">
          <Text dim>{text("empty", "Tell Iris what you are looking for, and the products of every shop you follow appear here.")}</Text>
          <Buttons>
            <Button say={text("exampleSay1", "Find me a warm wool sweater under 100 euro")}>{text("example1", "A wool sweater")}</Button>
            <Button say={text("exampleSay2", "Which shops do I follow for shopping?")}>{text("example2", "My shops")}</Button>
          </Buttons>
        </Card>
      );
    }
    return (
      <div>
        <Buttons>
          <Button primary={!shop} onClick={() => setShop("")}>{text("allShops", "All shops")}</Button>
          {shopNames.map((s) => <Button key={s} primary={shop === s} onClick={() => setShop(s)}>{s}</Button>)}
        </Buttons>
        <Buttons>
          <Button primary={sort === "best"} onClick={() => setSort("best")}>{text("best", "Best match")}</Button>
          <Button primary={sort === "low"} onClick={() => setSort("low")}>{text("low", "Cheapest")}</Button>
          <Button primary={sort === "high"} onClick={() => setSort("high")}>{text("high", "Priciest")}</Button>
          <Button primary={stockOnly} onClick={() => setStockOnly(!stockOnly)}>{text("inStock", "In stock")}</Button>
        </Buttons>
        {results.problems && results.problems.length ? (
          <Text dim>{text("notSearched", "Not searched")}: {results.problems.map(why).join("; ")}</Text>
        ) : null}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(9.5rem, 1fr))",
                      gap: ".8rem", marginTop: ".6rem" }}>
          {shown.map(tile)}
        </div>
        {!shown.length ? <Text dim>{text("noneFit", "Nothing fits these filters.")}</Text> : null}
      </div>
    );
  };

  // --- the cart ----------------------------------------------------------------------------------

  const cartView = () => {
    if (ordered) {
      return (
        <div>
          <Text>{text("readyToPay", "Ready. Open each shop, check the order and pay on its own page.")}</Text>
          {ordered.map((o) => (
            <Card key={o.shop} label={o.shop} title={price(o.total, o.currency)} icon="card">
              <Text dim>{how(o)}</Text>
              {o.steps && o.steps.length ? (
                <Buttons>
                  {o.steps.map((st, i) => <Button key={i} onClick={() => open(st.url)}>{`${i + 1}. ${st.title}`}</Button>)}
                </Buttons>
              ) : null}
              <Buttons>
                <Button primary onClick={() => open(o.checkout)}>{text("payAt", "Pay at")} {o.shop}</Button>
              </Buttons>
            </Card>
          ))}
          <Buttons><Button onClick={() => setOrdered(null)}>{text("done", "Done")}</Button></Buttons>
        </div>
      );
    }
    if (!cart.shops.length) return <Text dim>{text("cartEmpty", "The cart is empty.")}</Text>;
    return (
      <div>
        {cart.shops.map((s) => (
          <Card key={s.shop} label={s.shop} title={price(s.total, s.currency)} icon="pakket">
            {s.lines.map((l) => (
              <div key={l.id} style={{ display: "flex", alignItems: "center", gap: ".6rem", padding: ".45rem 0",
                                       borderTop: "1px solid var(--edge)" }}>
                {picture(l.image, "", { width: "2.8rem", height: "2.8rem", objectFit: "cover", borderRadius: ".4rem", flex: "none" }, `c${l.id}`)}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{l.title}</div>
                  <div style={{ color: "var(--dim)", fontSize: ".82rem" }}>
                    {l.variant ? `${l.variant}, ` : ""}{price(l.price, l.currency)}
                  </div>
                </div>
                <Buttons>
                  <Button onClick={() => setQty(l.id, l.qty - 1)}>-</Button>
                  <span style={{ minWidth: "1.5rem", textAlign: "center" }}>{l.qty}</span>
                  <Button onClick={() => setQty(l.id, l.qty + 1)}>+</Button>
                </Buttons>
              </div>
            ))}
          </Card>
        ))}
        {confirm ? (
          <Card label={text("sure", "Order this?")}>
            <Text>{text("sureText", "Iris opens each shop's checkout with everything in it. You pay there; nothing is paid here.")}</Text>
            <Buttons>
              <Button primary onClick={() => order()}>{text("yesOrder", "Yes, order")}</Button>
              <Button onClick={() => setConfirm(false)}>{text("notNow", "Not now")}</Button>
            </Buttons>
          </Card>
        ) : (
          <Buttons>
            <Button primary onClick={() => setConfirm(true)}>{text("order", "Order")} ({totals(cart.shops)})</Button>
            <Button onClick={() => act("clear", (d) => setCart(d.cart))}>{text("clear", "Empty the cart")}</Button>
          </Buttons>
        )}
      </div>
    );
  };

  // --- kept and ordered --------------------------------------------------------------------------

  const savedView = () => (saved.length ? (
    <Card label={text("keptLabel", "Kept to decide later")}>
      {saved.map((s) => (
        <div key={s.id} style={{ display: "flex", alignItems: "center", gap: ".6rem", padding: ".45rem 0",
                                 borderTop: "1px solid var(--edge)" }}>
          {picture(s.image, "", { width: "2.8rem", height: "2.8rem", objectFit: "cover", borderRadius: ".4rem", flex: "none" }, `s${s.id}`)}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.title}</div>
            <div style={{ color: s.price < s.first_price ? "var(--good)" : "var(--dim)", fontSize: ".82rem" }}>
              {s.shop}, {price(s.price, s.currency)}
              {s.first_price && s.price !== s.first_price ? ` (${text("was", "was")} ${price(s.first_price, s.currency)})` : ""}
              {s.available === false ? `, ${text("soldOut", "Sold out")}` : ""}
            </div>
          </div>
          <Buttons>
            <Button onClick={() => open(s.url)}>{text("view", "View")}</Button>
            <Button onClick={() => act(`unsave ${s.id}`, () => setSaved(saved.filter((x) => x.id !== s.id)))}>
              {text("forget", "Forget")}
            </Button>
          </Buttons>
        </div>
      ))}
    </Card>
  ) : <Text dim>{text("nothingKept", "Nothing kept yet. Tap Keep on a product to decide later.")}</Text>);

  const ordersView = () => (orders.length ? (
    <Card label={text("ordersLabel", "Ordered before")} icon="euro">
      {orders.map((o) => (
        <Row key={o.id} left={`${o.created.slice(0, 10)}  ${o.shop}: ${o.items.map((i) => `${i.qty} x ${i.title}`).join(", ")}`}
             right={price(o.total, o.currency)} />
      ))}
    </Card>
  ) : <Text dim>{text("noOrders", "Nothing ordered yet.")}</Text>);

  return (
    <Screen title={text("title", "Personal shopper")}
            subtitle={results.query ? `${text("for", "For")}: ${results.query}` : text("subtitle", "Every shop you like, in one place")}
            icon="pakket">
      <Stats>
        <Stat value={items.length} label={text("results", "results")} icon="chart" />
        <Stat value={shopNames.length} label={text("shops", "shops")} icon="server" />
        <Stat value={cart.count} label={text("inCart", "in the cart")} icon="pakket" />
        <Stat value={totals(cart.shops)} label={text("total", "total")} icon="card" />
      </Stats>
      <Buttons>
        <Button primary={view === "results"} onClick={() => setView("results")}>{text("tabResults", "Products")}</Button>
        <Button primary={view === "cart"} onClick={() => setView("cart")}>{text("tabCart", "Cart")} ({cart.count})</Button>
        <Button primary={view === "saved"} onClick={() => setView("saved")}>{text("tabSaved", "Kept")}</Button>
        <Button primary={view === "orders"} onClick={() => setView("orders")}>{text("tabOrders", "Orders")}</Button>
        <Button onClick={() => loadAll()}>{text("refresh", "Refresh")}</Button>
      </Buttons>
      {error ? <Text dim>{error}</Text> : null}
      {!bridge ? (
        <Buttons>
          <Button say={text("askResults", "Show my last shopping results")}>{text("tabResults", "Products")}</Button>
          <Button say={text("askCart", "What is in my shopping cart?")}>{text("tabCart", "Cart")}</Button>
          <Button say={text("askOrder", "Order my shopping cart")}>{text("order", "Order")}</Button>
        </Buttons>
      ) : null}
      {note && !error ? <Text dim>{note}</Text> : null}
      {view === "results" ? resultsView() : null}
      {view === "cart" ? cartView() : null}
      {view === "saved" ? savedView() : null}
      {view === "orders" ? ordersView() : null}
    </Screen>
  );
};
