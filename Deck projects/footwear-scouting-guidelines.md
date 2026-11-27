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

## Rules added in v8 (final version)
- The user may edit a version in Google Slides; the next version starts from those edits (read them in the browser and
  carry them into the builder, so the deck stays reproducible).
- Classification slides keep each sub-box title readable above the overlay, and the description sits centred in the
  space below the title.
- Speaker notes on classification slides add a short "how it works" section (one bullet per technology or route:
  mechanical and chemical recycling, mass balance, bio-based; NIR, hyperspectral, density, magnetic, delamination).
- Every slide's notes end with a glossary of the acronyms used on that slide or in its notes: full English name plus
  the Spanish version.
- The certifications matrix carries one plain-language line per certification saying what it guarantees
  (mass-balance accounting vs physical recycled content, social criteria or not).
- Cards for companies analysed before carry their own description; the "analysed before" pill already says the rest.
- Each conclusion must state a takeaway (e.g. what is ready for a short-term pilot vs medium-term watch), not a list of names.

## Rules added in v9 (review comments in Google Slides)
- Review comments live in the Slides comment panel; read them all (plus any direct text edits) before building, and map
  each one to its slide. The Slides "htmlpresent" view gives the full text of every slide and its notes in one page.
- When the user asks for more detail on a card ("parece vacía", "más detalles", "¿tenemos enlace?"), external sources
  are allowed: the company's own pages first, then reports such as the one already in the spreadsheet. Every new fact
  gets a source link on the card, and the additions are listed for the user so the spreadsheet can be updated.
- "Included in a report" is not enough as a use case: give implementation details (process, site, year, size, clients).
- Not commercialised is not the whole story: name pilots (with link) and which products of a company are on the market
  and which are still pilots.
- Wording check: use the precise technical term (e.g. carbon black pigment, not a loose translation).
- Card body: at most about 16 estimated lines; trim the lead before cutting facts.
- Conclusions may carry one source link, written as "(domain)." at the end.

## Rules added in v10
- Chemical formulas are written as formulas on slides (CO with subscript 2), applied by the builder to every slide; notes stay plain.
- A not-commercialised company can be highlighted when the user asks: the card says "En piloto" in a second pill, names
  the pilot site with a source link, and the card slide title becomes "Soluciones Destacadas".
- Companies analysed before get a first bullet starting "Novedad desde el último análisis:", stating why they are back.
- Every conclusion states the takeaway for the client (what to buy or pilot, and what to check first), and names the
  polymer (TPU, SBS, alternative to TR) when talking about a route.
- Claims about the client's own involvement (e.g. a partnership) are checked against the partner's own page before use.
- After each version, the source spreadsheet gets every new fact and its source link, appended to the existing cells,
  so the deck and the spreadsheet stay consistent.

## Review round on v10 (edit in place, no new version)
- When the user says they must edit the current file themselves, don't build a new version: read every comment
  (Slides "Show all comments" panel, then the page text), map each one to slide and section (click a comment with
  no quoted text to see its anchor), and deliver a Word action plan: summary table, then per item the comment,
  current text, proposed text ready to paste (deck language), why, and the spreadsheet/source check. Upload it to the
  project Drive folder. Change nothing in the deck or spreadsheet until the user approves.
- The spreadsheet is the north star: check every proposal against the live sheet, not only the local export. When a
  reviewer's claim about the sheet is wrong, say so and keep the deck.
- Anything new from outside the sheet goes in a separate "new findings" table with source and implication, plus a
  list of the spreadsheet cells to update after approval. Flag a sheet value that public sources don't support
  (e.g. a founding year) as a decision instead of copying it silently.
- Client waste-origin nomenclature: post-industrial (factory scrap, never part of a finished product), pre-consumo
  (finished but never used), post-consumo (after use). GRS "pre-consumer" (ISO 14021) = the client's post-industrial.
- Don't frame the client as running a pilot with material suppliers: they buy material. Keep "piloto" for a
  company's own maturity or a real consortium pilot.
- Every sticker claim (Tecnología, Input, Output) must be backed in the same card; grade codes and acronyms are
  explained in the notes glossary; data the source contradicts is not shown on slides.
- Conclusions carry no source links in the end (moved to notes), contrary to the v9 rule.

## Rules added in v11
- Before rebuilding, compare the live Slides text (htmlpresent view) with the last build: direct edits made in Slides
  (e.g. a note split into bullets placed in a free grid cell) must be carried into the code, or the rebuild loses them.
- Matrix notes are company bullets with the name in bold; on a grid with a free cell they sit in that cell.
- A company with two product ranges in different routes appears in both map categories; its card lead names both
  ranges and the bullets detail each one; the spreadsheet category gets both values (multi-select dropdown).
- A logo needing an extra attribute on a map (e.g. "also uses AI") gets a small caption plus a footnote on the map.
- Overflow trims go to the lead first, then technical details move to the speaker notes.
- Spreadsheet sync: exact wording fixes with Find and replace (check "Match entire cell contents" stays unticked);
  overwrite single values (years) directly; append new facts and their source links.

## Rules added in v12
- A company with ranges in several routes gets one map position per route and one card per route, each card placed
  in that route's section (e.g. a recycled range goes on the recycled cards slide, not on the bio-based card).
- A route's map box keeps its definition: if a range does not meet it (e.g. a GRS box and a range without GRS),
  widen the box label ("y alternativas") and its description rather than forcing the range in.
- Check which product a certification really covers (company-level ISCC PLUS for selected grades is not a
  certification of a specific range's content); say "no consta" / "a aclarar" where the maker publishes nothing.
- A slide can hold a single card (1-card width) when splitting a section by polymer.

## Open points
- None after v11 (2026-11-27). The wrap check still relies on the line estimate and SVG previews.
