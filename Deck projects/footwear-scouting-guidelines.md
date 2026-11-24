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

## Deck structure (same order as the reference decks)
1. Cover: "Scouting / <topic> / <month year>".
2. Full ecosystem map for the block: purple header per category, dashed boxes for
   "Soluciones Comercializadas" / "Soluciones en desarrollo", and logos.
3. Segmentation slides where useful, for example by technology or by method.
4. **Punto de Partida**: the same map showing only the solutions the client already knows
   (source column "previously analysed" = Yes). New facts about known companies go on
   "Novedades" cards.
5. **Ecosistema de Nuevas Tecnologías**: the map with the new solutions only.
6. For each group of companies to present, the new-solutions map with that group highlighted
   (others faded, boxes with no highlight covered by the grey 95% overlay), then the cards.
7. **Cards**: at least 2 companies per slide (2-up or 3-up layouts). Each card has the logo, a category pill,
   a lead paragraph with the company name in bold, then 3 bullets with a bold label.
8. Conclusions for each block: 4-5 boxes, each 2-3 lines.

## Content rules
- Copy is in Spanish.
- Every fact comes from the scouting spreadsheet. Nothing is invented, and gaps are stated as gaps
  ("No consta", "por validar").
- The user chooses which companies to highlight. They are never derived automatically.
- Logos come from each company's own website. When a company has no usable logo, its name goes in as text,
  and white logos are recoloured dark so they read on white.
- No en or em dashes. No personal contact details on slides.

## Delivery
- Export a PPTX version (`_v1`, `_v2`, ...) and copy it into the local project folder.
- Upload it to the shared Drive folder through the user's own Chrome session (the Drive connector is
  blocked by the organisation's admin policy). Check that the file appears in the folder.

## Open points for v2
- The user's additional details (pending).
- Check that the conclusion boxes wrap correctly in PowerPoint or Slides (the preview renderer does not wrap).
- Review the recoloured logos and the text stand-ins for companies without a logo.
