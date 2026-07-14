# Brand icon submission

Home Assistant (and therefore HACS) does **not** read integration icons from this
repository. Icons are served from the central
[home-assistant/brands](https://github.com/home-assistant/brands) repository,
keyed by the integration domain (`rnli_launches`). Until the icon is accepted
there, the HACS store list and **Settings → Devices & Services** show a generic
default icon. (The logo in the README still displays on the HACS info page,
because that page renders `README.md`.)

The files under [`custom_integrations/rnli_launches/`](custom_integrations/rnli_launches/)
are prepared to meet the brands requirements:

| File          | Size      | Purpose                        |
| ------------- | --------- | ------------------------------ |
| `icon.png`    | 256 × 256 | Square icon                    |
| `icon@2x.png` | 512 × 512 | High-DPI square icon           |
| `logo.png`    | 512 × 258 | Full "Lifeboats" logo (banner) |

## Submitting

> Only do this if you hold permission to use the RNLI logo — the brands repository
> asks you to confirm you have the right to submit a brand's artwork. See
> [`../LOGO_LICENSE.md`](../LOGO_LICENSE.md).

1. Fork [home-assistant/brands](https://github.com/home-assistant/brands).
2. Copy this folder into the fork:

   ```
   custom_integrations/rnli_launches/icon.png
   custom_integrations/rnli_launches/icon@2x.png
   custom_integrations/rnli_launches/logo.png
   ```

3. Open a pull request. In the description, state that the logo is used with the
   RNLI's written permission.
4. Once merged, the icon appears automatically in HACS and Home Assistant — no
   change to this integration is needed.
