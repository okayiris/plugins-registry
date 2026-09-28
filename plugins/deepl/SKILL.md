---
name: deepl
description: Translate text with the owner's own DeepL key through the translate command of the deepl plugin. Into the owner's usual language or any other of about thirty, with a formal form where the language has one, and the monthly usage.
whenToUse: When the owner asks to translate something, wants to know what a text in another language says, or wants a message written in another language (write it, then translate it). You can translate short phrases yourself; use DeepL when the owner asks for it or the text is long or formal.
---

# deepl (command: translate)

```sh
translate Goedemorgen allemaal                # into the owner's usual language
translate to german "See you on Monday"
translate formal to dutch "How are you?"      # u in Dutch, Sie in German
translate usage                               # characters used this month
translate languages
translate key ask                             # the owner pastes a key in the vault
```

- Say the translation back and offer to copy or send it; sending goes through the messaging plugins.
- A free key has 500,000 characters a month. Mention the usage only when it is close to the limit.
