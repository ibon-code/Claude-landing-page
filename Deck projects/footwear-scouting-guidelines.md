# Footwear materials scouting deck: working guidelines

How we build this scouting deck, so that v2 starts from where v1 ended. This file holds no client
data on purpose: company lists, source spreadsheets, decks and file locations stay on the local Mac.

## Goal
A technology scouting deck for a client in two blocks:
1. **Sorting** of footwear: material identification and separation/delamination.
2. **Materials**: recycled, mass-balance and bio-based TPU and SBS (TR).

The format must copy the client's earlier scouting decks **very faithfully**. Those decks are the
style and structure reference. We do not redesign them.

## Method
- **Skeleton**: every slide is a clone of a native slide from a previous scouting deck, with the same
  layout, fonts, colours, header logos and shadows. Only text, logos and panel geometry change, and the
  text stays native and editable.
- **Stack**: Python + python-pptx for the cloning and filling. The ppt-master skill supplies the controls
  (delivery check, text read-back, PNG previews), and the local PPT Automation workspace supplies the
  dash fix and the verify step for emails, dashes and forbidden template words.
- **Done means checked**: delivery check has 0 errors, verify is clean, and every PNG preview has been looked at.

## Deck structure (v2, modelled on the richer of the two reference decks)
1. Cover: "Scouting / <topic> / <month year>".
2. For each block:
   - **Classification slide**: the block's map with every sub-category covered by the grey 95% overlay
     and a short bold description of what that category means.
   - **One consolidated map**: purple header per category, dashed sub-category boxes, logos.
     **Red frame = mature company** (source column "Empresa" = mature), **lavender fill = analysed
     before** (source column "previously analysed" = Yes), and a small legend at the bottom right.
     No separate "starting point" or "new solutions" maps: everything is on this one map.
   - **Matrix slide** (like the reference "Inputs" slide): small header bars with the logos that
     match each one, e.g. which materials each sorting solution recognises, or certifications.
   - **Interlude per category**: the same map with the other categories faded out, and inside the
     active one, the companies that are not presented faded.
   - **Cards**: at least 2 per slide (2-up or 3-up). Purple category pill above the card (plus an
     "analysed before" pill when it applies), logo, then stickers: green Input, blue Output, yellow
     third fact (capacity, technology result or certification), then a lead paragraph with the company
     name in bold and 2 or 3 bullets.
   - **Conclusions**: 5 boxes, each 2 or 3 lines.

## Content rules
- Copy is in Spanish.
- Every fact comes from the scouting spreadsheet. Nothing is invented, and gaps are stated as gaps
  ("No consta", "por validar").
- The user chooses which companies to highlight. They are never derived automatically.
- Logos come from each company's own website. When a company has no usable logo, its name goes in as text,
  and white logos are recoloured dark so they read on white.
- No en or em dashes. No personal contact details on slides.

## Google Slides
- Faded logos are baked into the PNG pixels (no picture transparency, which imports unreliably).
- Text boxes are sized so nothing depends on shrink-on-overflow; logos are at most 800 px wide.
- Wrapping is checked in a real renderer (Keynote PDF export), because the SVG preview does not wrap text.

## Delivery
- Export a PPTX version (`_v1`, `_v2`, ...) and copy it into the local project folder.
- Upload it to the shared Drive folder through the user's own Chrome session (the Drive connector is
  blocked by the organisation's admin policy). Check that the file appears in the folder.

## Logos
- Take them from each company's official site; when the reference decks already contain a company's
  logo, reuse that exact file so it matches what the client has seen.
- Crop taglines and division labels; add a small name caption under bare symbols.
- Recolour only logos that exist solely in white, and list those for the user to review.

## Rules added in v4
- **Classification model (v5, user decision)**: keep the v3 maps, with sub-boxes by technique (sorting) or by
  polymer (materials). A commercialised / not-commercialised split and separate segmentation slides were
  tried in v4 and rejected as messy.
- **Commercial status (v6)**: inside each technique or polymer box, the logos sit under small italic subtitles
  "Comercializadas" and "No comercializadas" (an empty group is omitted); wide, short boxes place the two
  groups side by side with a thin dashed divider. The interludes inherit the split. Subtitles are centred over
  their own group and sit a few points below the box title.
- **Commercialised means the product is on the market**, not that the company is mature: a mature company
  launching a new technology can be "not commercialised", and a startup with a product on sale is "commercialised".
  Check the spreadsheet column against its own sources, and against reliable external sources when in doubt;
  report every change to the user so they can update the spreadsheet.
- **Speaker notes** on every slide: concise bullets from the spreadsheet only, sized for a ~30 minute talk.
- **Cards** carry real content from the spreadsheet (like the model card slide): lead paragraph plus 2 to 4
  bullets. When the spreadsheet's own source links show a footwear use case, one bullet describes it and links
  that source. **No external sources** for card content; no use case in the sources means no bullet and no link.
- **One body size**: Arial 9 for all body text (cards, descriptions, notes under matrices); bold labels 9;
  only titles, small stickers, captions and the legend differ.
- **Logo grid**: fixed column pitch per box, short rows centred, shared baseline per row; tinted logo
  backdrops are removed so the "analysed before" fill shows (that fill is a light lavender).
- Conclusions highlight what the scouting adds, not which companies were already analysed.
- A company the user marks as "not the right use case" is not highlighted and not cited in conclusions.

## Open points after v7
- User to decide whether to align the spreadsheet column with the v7 sanity check.
