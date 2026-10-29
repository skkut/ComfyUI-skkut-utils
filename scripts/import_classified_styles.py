#!/usr/bin/env python3
"""Build the curated style file from the Classified_Styles Google Sheet.

The sheet is compiled and shared publicly by u/Dear-Spend-2865 and is read
directly from its published CSV endpoint, so the same import can run in CI.
This script does *not* touch ``skutils_style_selector/styles.json``; it writes
``scripts/classified_styles_v18_curated.json`` for review and later merging.

What the import does:

* removes the leading ``<style name>:`` prefix and any short leading
  restatement of the style name from each wildcard prompt;
* drops rows whose style already exists in the bundled library;
* drops rows listed as renamed / reworked counterparts of bundled styles in
  ``scripts/classified_styles_v18_renames.json``;
* collapses exact duplicate prompts and cross-name prefix near-duplicates;
* maps the sheet's categories to the bundled library's sections, adding
  ``Illustration`` and ``Character & Creature Design`` where the sheet has
  genuinely new groupings;
* gives every output style a non-empty section-level baseline negative.

Run locally against a downloaded CSV::

    python scripts/import_classified_styles.py --input Classified_Styles.csv

Run against the live sheet (the default)::

    python scripts/import_classified_styles.py

Verify that the committed output still matches the live sheet::

    python scripts/import_classified_styles.py --check
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import unicodedata
import urllib.request
from collections import Counter
from difflib import SequenceMatcher, unified_diff
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "scripts" / "classified_styles_v18_curated.json"
DEFAULT_RENAMES = REPO_ROOT / "scripts" / "classified_styles_v18_renames.json"
DEFAULT_EXISTING = REPO_ROOT / "skutils_style_selector" / "styles.json"

SOURCE_NAME = "u/Dear-Spend-2865"
SOURCE_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1fb2yD74gqT_BxmBpkOMX2V7gSj_A8RQ0/gviz/tq?tqx=out:csv&sheet=Classified_Styles"
)
SHEET_LABEL = "styles_wildcard_v18_krea2_classified / Classified_Styles"

REQUIRED_COLUMNS = (
    "Order",
    "Category",
    "Medium",
    "Family / Subcategory",
    "Era / Period",
    "Style Name",
    "Wildcard Style",
    "Original Row",
)

SECTION_ORDER = (
    "Anime",
    "Cartoon",
    "Comics",
    "Drawing",
    "Painting",
    "Digital Painting",
    "Printmaking",
    "Craft & Collage",
    "Photography",
    "Design",
    "Cover Art",
    "3D Render",
    "Sculpture & Toys",
    "Stop-Motion & Puppetry",
    "Video Games",
    "Illustration",
    "Character & Creature Design",
)

# Section-level baseline negatives. These are deliberately broad: they keep a
# style recognisable without fighting the subject the user brings to it.
SECTION_NEGATIVES = {
    "Anime": (
        "photorealistic skin pores, 3D CGI render, oil-painting brushwork, "
        "western cartoon proportions, sketchy unfinished linework"
    ),
    "Cartoon": (
        "photorealistic anatomy, 3D CGI render, oil-painting texture, "
        "anime large-eye proportions, gritty horror shading"
    ),
    "Comics": (
        "photorealistic skin pores, 3D CGI render, anime proportions, "
        "soft watercolor wash, sketchy unfinished linework"
    ),
    "Drawing": (
        "photorealistic rendering, 3D CGI render, oil-painting impasto, "
        "digital airbrush gloss, flat vector fills"
    ),
    "Painting": (
        "smooth airbrushed gradients, flat vector fill, photorealistic skin pores, "
        "3D CGI plastic sheen, crisp uniform lines"
    ),
    "Digital Painting": (
        "flat cartoon fill, simple geometric shapes, rough sketch lines, "
        "3D CGI plastic sheen, cluttered foreground"
    ),
    "Printmaking": (
        "flat digital color fill, smooth airbrushed gradients, photorealistic texture, "
        "3D CGI render, loose sketchy lines"
    ),
    "Craft & Collage": (
        "photorealistic texture, 3D CGI plastic sheen, smooth airbrushed gradients, "
        "uniform seamless rendering, single consistent medium"
    ),
    "Photography": (
        "illustration, painting, 3D CGI render, cartoon proportions, sketch lines, "
        "surreal distortion"
    ),
    "Design": (
        "photorealistic texture, 3D CGI render, painterly brushstrokes, gritty grain, "
        "ornate clutter"
    ),
    "Cover Art": (
        "photorealistic texture, 3D CGI plastic sheen, smooth airbrushed gradients, "
        "crude sketch lines, muted muddy palette"
    ),
    "3D Render": (
        "painterly brushstrokes, 2D illustration, flat vector fill, visible canvas texture, "
        "photographic grain"
    ),
    "Sculpture & Toys": (
        "photorealistic human proportions, realistic facial detail, matte clay texture, "
        "flat 2D illustration, photoreal skin"
    ),
    "Stop-Motion & Puppetry": (
        "smooth digital perfection, photorealistic skin pores, 3D CGI plastic sheen, "
        "flat vector fill, crisp uniform lines"
    ),
    "Video Games": (
        "photorealistic texture, gritty horror shading, muted muddy palette, "
        "flat 2D illustration, rough sketch lines"
    ),
    "Illustration": (
        "photorealistic skin pores, 3D CGI render, crude low-detail rendering, "
        "muddy desaturated palette, cluttered composition"
    ),
    "Character & Creature Design": (
        "photorealistic human proportions, flat 2D illustration, inconsistent anatomy, "
        "extra limbs, muddy desaturated palette"
    ),
}

CATEGORY_SECTIONS = {
    "Anime": "Anime",
    "Manga, Manhwa and Manhua": "Anime",
    "Cartoon and Animation": "Cartoon",
    "Character and Creature Design": "Character & Creature Design",
    "Comics": "Comics",
    "Game Art": "Video Games",
    "Illustration": "Illustration",
    "Drawing and Line Art": "Drawing",
    "Photography and Cinema": "Photography",
    "Printmaking": "Printmaking",
    "Digital, Graphic and Mixed Media": "Design",
    "Other and Cross-Media": "Design",
}

# ---------------------------------------------------------------------------
# Section assignment rules
# ---------------------------------------------------------------------------

PRODUCT_PHOTO_RE = re.compile(
    r"\b(?:toys?|dolls?|action figures?|figurines?|collectible figures?|model kits?|"
    r"lego|playmobil|funko|plush|stuffed animals?)"
    r"(?:\s+\w+){0,5}\s+(?:photo|photos|photograph|photographs|photography)\b"
)

PHOTO_NOUN_RE = re.compile(r"\b(?:photo|photos|photograph|photographs|photography)\b")
COVER_TERM_RE = re.compile(
    r"\b(?:posters?|covers?|key art|box art|cover art|cover illustration|cover design|"
    r"album art|book jacket|dust jacket|one sheet|key visual)\b"
)
STRONG_3D_RE = re.compile(
    r"\b(?:3d|three dimensional)\s+(?:render|rendering|illustration|animation|art)\b"
    r"|\b(?:cgi|cg)\s+render(?:ing)?\b"
    r"|\bunreal engine\b"
    r"|\bblender render(?:ing)?\b"
)
WEAK_3D_RE = re.compile(r"\brender(?:s|ed|ing)?\b|\blow poly\b|\bwire ?frame\b")

DESIGN_PRIORITY_RE = re.compile(
    r"\b(?:"
    r"(?:game|level|world|environment|prop|weapon|vehicle|automotive|product|"
    r"industrial|graphic|communication|information|ui|ux|hud|interface|logo|icon|"
    r"sticker|emblem|tattoo|pattern|textile|fashion|fabric|wallpaper|jewelry|"
    r"jewellery|shoe|sneaker|watch|furniture|interior|architectural|costume|"
    r"production|set|exhibit|title|book|album|magazine|editorial|web|infographic|"
    r"diagram|map)\s+design"
    r"|motion graphics|kinetic typography|generative design|parametric design"
    r"|algorithmic art|generative art|data visuali[sz]ation"
    r"|branding|packaging|typography|infographics?|logos?|ui|ux|hud|interface"
    r"|surface pattern|pattern design|icon set"
    r")\b"
)

CHARACTER_RE = re.compile(
    r"\b(?:character|creature|monster|mascot|kaiju|alien|robot|mecha|cyborg|mutant|beast)"
    r"\s+(?:designs?|design sheets?|concepts?|concept art|art|illustrations?|lineups?|"
    r"line ups?|turnarounds?|reference|references|sheets?|studies|study)\b"
    r"|\b(?:pose|expression|model)\s+sheets?\b"
    r"|\bsilhouette\s+(?:study|studies)\b"
    r"|\bcolou?r callout sheets?\b"
)

STOP_MOTION_RE = re.compile(
    r"\bstop[\s-]?motion\b|\bclaymation\b|\bclay animation\b|\bpuppetry\b|\bmarionettes?\b"
    r"|\bpuppets?\b|\blaika\b|\baardman\b|\bwallace and gromit\b|\bcoraline\b|\bmuppets?\b"
    r"|\brankin bass\b|\bwill vinton\b|\bsvankmajer\b|\brobot chicken\b|\barmatures?\b"
)

CRAFT_RE = re.compile(
    r"\bkintsugi\b|\borigami\b|\bkirigami\b|\bquilling\b|\bmosaic\b"
    r"|\bstained glass\b|\bcollages?\b|\bmixed media\b|\bassemblages?\b|\bdecoupage\b"
    r"|\bscrapbooks?\b|\bembroidery\b|\bcross stitch\b|\bneedlepoint\b|\bknitting\b"
    r"|\bknitted\b|\bcrochet\b|\bneedle felt\b|\bfelted\b|\bfelt craft\b|\bfelt art\b"
    r"|\bfelt sculpture\b|\bbatik\b|\btie[\s-]?dye\b|\btextiles?\b|\bweaving\b"
    r"|\btapestry\b|\bmacrame\b|\bpaper[\s-]*(?:cutouts?|cut outs?|cuts?|art|craft|"
    r"sculpture|strips?|mache|papercraft)\b|\bpapier[\s-]*mache\b|\bpapercraft\b"
    r"|\bcardboard\b|\bresin\b"
    r"|\bbeadwork\b|\bbeaded\b|\bbeads?\b|\bsequins?\b|\byarn\b|\bwool\b|\bfabric\b"
    r"|\bsewing\b|\bpatchwork\b|\bapplique\b|\bquilting\b|\bcakes?\b|\bfondant\b"
    r"|\bicing\b|\bsugar craft\b|\bchocolate\b|\bfood art\b|\bflower arrangement\b"
    r"|\bikebana\b|\bsoap carving\b|\bsoap sculpture\b|\bsand art\b|\bsand sculpture\b"
    r"|\bice sculpture\b|\bgingerbread\b|\bazulejos?\b"
)

SCULPTURE_RE = re.compile(
    r"\b(?:sculptures?|sculptural|statues?|statuary|figurines?|action figures?|"
    r"collectible figures?|porcelain|ceramics?|pottery|raku|terracotta|plaster|"
    r"marble (?:statue|sculpture|bust)|hellenistic marble|bronze (?:sculpture|bust)|"
    r"relief carvings?|low relief|bas relief|wood carvings?|stone carvings?|"
    r"jade carvings?|clay figures?|maquettes?|scale models?|handcrafted diorama|"
    r"miniature diorama|3d printed sculptures?|vinyl sculptures?|designer vinyl|"
    r"art toys?|collectible toys?|lego|playmobil|funko|nendoroid|amiibo|gunpla|"
    r"model kits?|plush|stuffed animals?|bronze patina|tabletop miniatures?)\b"
)

ANIME_RE = re.compile(
    r"\banime\b|\bmanga\b|\bmanhwa\b|\bmanhua\b|\bwebtoons?\b|\blight novels?\b"
    r"|\brofan\b|\bdonghua\b|\bshonen\b|\bshoujo\b|\bshojo\b|\bseinen\b|\bjosei\b"
    r"|\bkodomo\b|\bgekiga\b|\bsakuga\b|\bgenga\b|\bdoujin\b|\bisekai\b|\bmecha\b"
    r"|\bchibi\b|\bmoe\b|\botome\b|\bbishoujo\b|\bbishounen\b|\byaoi\b|\byuri\b"
    r"|\bscreentone\b|\bghibli\b|\bkyo ?ani\b|\bkyoto animation\b|\bmappa\b"
    r"|\bwit studio\b|\bufotable\b|\bmadhouse\b|\bgainax\b"
    r"|\btrigger (?:style|animation|studio)\b|\bstudio trigger\b"
    r"|\bbones (?:style|animation|studio)\b|\bstudio bones\b"
    r"|\bpierrot (?:style|animation|studio)\b|\bstudio pierrot\b"
    r"|\btoei (?:style|animation|studio)\b|\bstudio toei\b"
    r"|\bsunrise (?:style|animation|studio)\b|\bstudio sunrise\b"
    r"|\bproduction i g\b"
    r"|\bshaft (?:style|animation|studio)\b|\bstudio shaft\b"
    r"|\bnaruto\b|\bone piece\b|\bbleach\b(?!\s+bypass)|\bdragon ball\b"
    r"|\bsailor moon\b|\bjojo\b|\bevangelion\b|\battack on titan\b|\bdemon slayer\b"
    r"|\bjujutsu kaisen\b|\bmy hero academia\b|\bchainsaw man\b|\bfrieren\b"
    r"|\bsolo leveling\b|\bpokemon\b|\bdoraemon\b|\bastro boy\b|\bgundam\b"
    r"|\bgranblue fantasy\b|\bamano\b|\bshingo araki\b"
    r"|\bmacross\b|\bcardcaptor\b|\binuyasha\b|\branma\b|\blupin\b"
    r"|\bcowboy bebop\b|\bsamurai champloo\b|\bakira\b|\bghost in the shell\b"
    r"|\bspirited away\b|\btotoro\b|\bponyo\b|\bhowl\b|\bprincess mononoke\b"
    r"|\bperfect blue\b|\bpaprika\b|\bmillennium actress\b|\btokyo godfathers\b"
)

GAME_RE = re.compile(
    r"\bgames?\b|\bgaming\b|\bvideo games?\b|\bpixel art\b|\b(?:8|16|32)[\s-]?bit\b"
    r"|\bn64\b|\bps[1-5]\b|\bplaystation\b|\bnintendo\b|\bsega\b|\bdreamcast\b"
    r"|\bgame boy\b|\bnes\b|\bsnes\b|\batari\b|\bcommodore 64\b|\barcade\b"
    r"|\bjrpg\b|\brpg\b"
    r"|\bmmo\b|\bmoba\b|\bfps\b|\bopen world\b|\bbattle royale\b|\broguelike\b"
    r"|\bmetroidvania\b|\bsoulslike\b|\bplatformer\b|\bshmup\b|\bbullet hell\b"
    r"|\bvisual novel\b|\bvoxel\b|\bxbox\b"
    r"|\bmario\b|\bzelda\b|\bkirby\b(?!\s+krackle)|\bmetroid\b|\bsonic the hedgehog\b"
    r"|\bminecraft\b|\bfortnite\b|\boverwatch\b|\bwarcraft\b|\bstarcraft\b"
    r"|\bdiablo\b|\bleague of legends\b|\bdota\b|\bcounter[\s-]?strike\b"
    r"|\bcall of duty\b|\bgrand theft auto\b|\bgta\b|\bred dead\b|\bskyrim\b"
    r"|\belder scrolls\b|\bfallout\b|\bmass effect\b|\bdark souls\b|\belden ring\b"
    r"|\bbloodborne\b|\bsekiro\b|\bwitcher\b|\bcyberpunk 2077\b|\bassassins creed\b"
    r"|\bresident evil\b|\bsilent hill\b|\bmetal gear\b|\bfinal fantasy\b"
    r"|\bkingdom hearts\b|\bpersona\b|\bfire emblem\b|\bxenoblade\b"
    r"|\banimal crossing\b|\bstardew valley\b|\bterraria\b|\bhollow knight\b"
    r"|\bhades\b|\bceleste\b|\bundertale\b|\broblox\b|\bgenshin impact\b"
    r"|\bhonkai\b|\bgranblue fantasy\b|\bstreet fighter\b|\btekken\b"
    r"|\bmortal kombat\b|\bsmash bros\b|\bthe sims\b|\bsims\b"
)

COMICS_RE = re.compile(
    r"\bcomics?\b|\bcomix\b|\bgraphic novels?\b|\bbande dessinee\b|\bbd\b"
    r"|\bfumetti\b|\bfumetto\b|\bsuper ?hero(?:es)?\b|\bsuper ?villains?\b"
    r"|\bwebcomics?\b|\bmanara\b|\bcrepax\b|\bligne claire\b|\bfranco belgian\b"
    r"|\bherge\b|\bmoebius\b|\bbill wat+erson\b|\bcalvin and hobbes\b"
    r"|\bhugo pratt\b|\balex ross\b"
)

CARTOON_RE = re.compile(
    r"\bcartoons?\b|\banimations?\b|\banimated\b|\bcel animation\b"
    r"|\bsaturday morning cartoon\b|\brubber hose\b|\bgag cartoon\b"
    r"|\beditorial cartoons?\b|\bnewspaper cartoons?\b|\bweb cartoons?\b"
    r"|\btv cartoons?\b|\btelevision cartoons?\b|\bclone wars\b|\brotoscop(?:e|ed|ing)\b"
    r"|\b2d animation\b|\btraditional animation\b|\bhand drawn animation\b"
    r"|\bcalarts\b|\bdisney\b|\bpixar\b|\bdreamworks\b|\barcane\b|\btartakovsky\b"
    r"|\bhanna barbera\b|\blooney tunes\b|\bmerrie melodies\b|\btom and jerry\b"
    r"|\bscooby\b|\bflintstones\b|\bjetsons\b|\bsimpsons\b|\bsouth park\b"
    r"|\bfamily guy\b|\bfuturama\b|\brick and morty\b|\bgravity falls\b"
    r"|\badventure time\b|\bsteven universe\b|\bpowerpuff\b|\binvader zim\b"
    r"|\bspongebob\b|\bdexters laboratory\b|\bspider verse\b|\bpeanuts\b"
    r"|\bsnoopy\b|\bbruce timm\b|\btex avery\b|\bbean mouth\b"
    r"|\bupa\b|\btoons?\b"
)

PRINTMAKING_RE = re.compile(
    r"\bscreen ?prints?\b|\bscreen ?printing\b|\bserigraph(?:y|s)?\b"
    r"|\bsilkscreens?\b|\blithographs?\b|\blithography\b|\bchromolithographs?\b"
    r"|\bwoodcuts?\b|\bwoodblocks?\b|\bwood engravings?\b|\blinocuts?\b|\blinoprints?\b"
    r"|\bblock ?prints?\b|\brelief prints?\b|\bintaglio\b|\betchings?\b"
    r"|\bengravings?\b|\baquatint\b|\bmezzotint\b|\bdrypoint\b|\bmonotypes?\b"
    r"|\bmonoprints?\b|\bcollagraphs?\b|\brisographs?\b|\briso print\b"
    r"|\bletterpress\b|\bcyanotype\b|\bphotogravure\b|\bcollotype\b"
    r"|\bwoodburytype\b|\bgiclee\b|\bmokuhanga\b|\bukiyo e\b|\bben day\b"
    r"|\bhalftones?\b|\boffset (?:print|lithography)\b|\bstencil prints?\b"
    r"|\brubber stamp print\b|\bzincograph\b|\bcopperplate\b|\bsteel engraving\b"
    r"|\bphoto etching\b|\bphotolithograph\b|\b3d prints?\b|\banaglyph\b"
    r"|\bpochoir\b|\bvisionary prints?\b|\bphotochrom\b"
)

COVER_RE = re.compile(
    r"\bposters?\b|\bcovers?\b|\bbook covers?\b|\balbum covers?\b|\bmagazine covers?\b"
    r"|\bmovie posters?\b|\bfilm posters?\b|\btheatrical posters?\b|\bkey art\b"
    r"|\bbox art\b|\bcover art\b|\bcover illustrations?\b|\bcover designs?\b"
    r"|\bposter art\b|\bposter illustrations?\b|\bposter designs?\b|\balbum art\b"
    r"|\bbook jackets?\b|\bdust jackets?\b|\bone sheets?\b|\bkey visuals?\b"
    r"|\bsaul bass\b|\bairline (?:travel )?illustrations?\b"
)

DESIGN_GENERIC_RE = re.compile(
    r"\bdesign\b|\blogos?\b|\bbranding\b|\btypography\b|\bpackaging\b"
    r"|\binfographics?\b|\bui\b|\bux\b|\bhud\b|\binterface\b|\bisometric\b"
    r"|\bop art\b|\bmoire\b|\btopographic\b|\bvoysey\b|\bkurzgesagt\b"
    r"|\bcorporate memphis\b|\bmemphis\b|\bmidcentury\b|\bmid century\b"
    r"|\bfrutiger aero\b|\bbutcher billy\b|\bbauhaus\b|\bswiss style\b"
    r"|\binternational typographic\b|\bflat vector\b|\bvector art\b"
    r"|\bvector illustrations?\b|\bgradient mesh\b|\bpatterns?\b"
    r"|\bsurface pattern\b|\bminimalist line art\b|\bminimalism\b|\bgradients?\b"
    r"|\bnegative space\b|\bcamille walala\b|\barts and crafts\b"
)

PHOTOGRAPHY_RE = re.compile(
    r"\b(?:photo|photos|photograph|photographs|photography|photographic)\b"
    r"|\bfilm stills?\b|\bmovie stills?\b|\bcinematic stills?\b|\bsitcom stills?\b"
    r"|\bfilm photos?\b|\bfilm photography\b|\bfilm grains?\b|\bfilm noirs?\b"
    r"|\banalog film\b|\b35\s*mm\b|\b8\s*mm\b|\b16\s*mm\b|\bsuper 8\b|\bvhs\b"
    r"|\bbetacam\b|\bfootage\b|\bcctv\b|\bbody ?cam\b|\bdash ?cam\b|\bwebcam\b"
    r"|\bsurveillance camera\b|\bcamcorders?\b|\bpolaroids?\b|\binstant photos?\b"
    r"|\bbokeh\b|\bfish ?eye\b|\btilt shift\b|\blong exposure\b|\bmotion blur\b"
    r"|\bdepth of field\b|\bgolden hour\b|\bblue hour\b|\blow key\b|\bhigh key\b"
    r"|\brembrandt lighting\b|\bbutterfly lighting\b|\bdutch angle\b|\bhalation\b"
    r"|\bphotojournalism\b|\btintype\b|\bdaguerreotype\b|\bwet plate\b"
    r"|\balbumen print\b|\bgelatin silver\b|\bplatinum print\b|\bpalladium print\b"
    r"|\bphotogram\b|\blumen print\b|\bchemigram\b|\bgum bichromate\b|\bsalt print\b"
    r"|\bchromogenic\b|\bcibachrome\b|\bdye transfer\b|\bcross process(?:ed)?\b"
    r"|\blomography\b|\bholga\b|\btoy camera\b|\bdisposable camera\b"
    r"|\bpoint and shoot\b|\bsnapshot\b|\bselfie\b|\bheadshot\b|\bcosplay\b"
    r"|\binstagram\b|\bvogue\b|\bplayboy\b|\bgq\b|\blookbook\b|\bboudoir\b"
    r"|\bwedding\b|\bneon noir\b|\bfashion editorials?\b|\bbeauty editorials?\b"
    r"|\bglamour editorials?\b"
    r"|\b(?:fashion|beauty|glamour|editorial|studio|environmental)\s+portraits?\b"
)

DRAWING_RE = re.compile(
    r"\bdrawings?\b|\bcrayons?\b|\bcoloring books?\b|\bcolou?red pencils?\b"
    r"|\bpencil (?:drawings?|sketch(?:es)?|art|illustrations?)\b|\bgraphite\b"
    r"|\bcharcoals?\b|\bink drawings?\b|\bink sketch(?:es)?\b|\bink illustrations?\b"
    r"|\bink art\b|\bink line\b|\bpen and ink\b|\bmarker (?:drawings?|illustrations?|"
    r"art|rendering)\b|\bpastel (?:drawings?|illustrations?|art|portraits?)\b"
    r"|\boil pastels?\b|\bsoft pastels?\b|\bchalk pastels?\b|\bchalk drawings?\b"
    r"|\bchalk art\b|\bchalk\b|\bscratchboard\b|\bsilverpoint\b|\bmetalpoint\b"
    r"|\bconte\b|\bdoodles?\b|\bsketch(?:es)?\b|\bline drawings?\b|\bline art\b"
    r"|\blinework\b|\bcrosshatch(?:ing|ed)?\b|\bhatching\b|\bstippling\b"
    r"|\bscribbles?\b|\bcalligraph(?:y|ic)\b|\bbrush pens?\b|\bcroquis\b"
    r"|\bgesture drawings?\b|\bfigure drawings?\b|\blife drawings?\b"
    r"|\banatomy stud(?:y|ies)\b|\bone line\b|\bcontinuous line\b"
    r"|\bcontour drawings?\b|\bblind contour\b|\bsketchbooks?\b|\bblueprints?\b"
    r"|\bstick figures?\b|\bcoloring book line art\b|\bcaricatures?\b"
    r"|\btechnical drawings?\b|\barchitectural drawings?\b|\bmechanical drawings?\b"
)

PAINTING_SPECIAL_RE = re.compile(
    r"\bbiomechanical\b|\bgiger\b|\bgraffiti\b|\bstreet art\b|\bspray paint\b|\bmurals?\b"
)


def match_key(name: str) -> str:
    """Return a lower-case, accent-free, space-padded key for matching."""
    text = unicodedata.normalize("NFKD", name).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " " + " ".join(text.split()) + " "


def assign_section(name: str, category: str, medium: str) -> str:
    """Map one sheet row to the most relevant library section."""
    key = match_key(name)

    # A photograph of a toy, doll, figure or model is a product photograph;
    # subject rules must not turn it into a sculpture.
    if PRODUCT_PHOTO_RE.search(key):
        return "Photography"

    # Strong design language wins over the medium, except when the name is
    # explicitly a photograph (Interior Design Photography) rather than a
    # design (Interior Design).
    if DESIGN_PRIORITY_RE.search(key):
        if PHOTO_NOUN_RE.search(key) and not COVER_TERM_RE.search(key):
            return "Photography"
        return "Design"

    if CHARACTER_RE.search(key):
        return "Character & Creature Design"

    if STOP_MOTION_RE.search(key):
        return "Stop-Motion & Puppetry"

    # Pointillism is a painting technique, not a mosaic craft.
    if CRAFT_RE.search(key) and not (
        re.search(r"\bmosaic\b", key) and "pointillism" in key
    ):
        return "Craft & Collage"

    if re.search(r"\bdioramas?\b", key) and not WEAK_3D_RE.search(key):
        return "Sculpture & Toys"
    if SCULPTURE_RE.search(key):
        return "Sculpture & Toys"
    if re.search(r"\btoys?\b", key) and not re.search(
        r"\btoy\s+(?:camera|photograph|photography|photo|story)\b", key
    ):
        return "Sculpture & Toys"
    if re.search(r"\bdolls?\b", key):
        return "Sculpture & Toys"

    if STRONG_3D_RE.search(key):
        return "3D Render"

    if ANIME_RE.search(key):
        return "Anime"
    if GAME_RE.search(key):
        return "Video Games"
    if COMICS_RE.search(key):
        return "Comics"
    if CARTOON_RE.search(key):
        return "Cartoon"
    if WEAK_3D_RE.search(key):
        return "3D Render"

    if PRINTMAKING_RE.search(key):
        return "Printmaking"
    if COVER_RE.search(key) or medium == "Travel and Poster Illustration":
        return "Cover Art"
    if DESIGN_GENERIC_RE.search(key):
        return "Design"
    if PHOTOGRAPHY_RE.search(key):
        return "Photography"
    if DRAWING_RE.search(key):
        return "Drawing"
    if PAINTING_SPECIAL_RE.search(key):
        return "Painting"

    if category in ("Anime", "Manga, Manhwa and Manhua"):
        return "Anime"
    if category == "Cartoon and Animation":
        return "Cartoon"
    if category == "Character and Creature Design":
        return "Character & Creature Design"
    if category == "Comics":
        return "Comics"
    if category == "Game Art":
        return "Video Games"
    if category == "Drawing and Line Art":
        return "Drawing"
    if category == "Painting":
        return "Digital Painting" if medium == "Digital Painting" else "Painting"
    if category == "Photography and Cinema":
        return "Photography"
    if category == "Printmaking":
        return "Printmaking"
    if category == "Sculpture and Material Art":
        return "Craft & Collage" if medium == "Craft and Physical Media" else "Sculpture & Toys"
    if category == "Illustration":
        if medium in ("Poster and Cover Art", "Travel and Poster Illustration"):
            return "Cover Art"
        return "Illustration"
    if category in ("Digital, Graphic and Mixed Media", "Other and Cross-Media"):
        return "Design"

    raise ValueError(f"unknown sheet category: {category!r} (style {name!r})")


# ---------------------------------------------------------------------------
# Prompt cleaning and deduplication
# ---------------------------------------------------------------------------


def _norm_words(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", text).strip()


def _compact(text: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", text).casefold())


def strip_name_prefix(name: str, prompt: str) -> str:
    """Remove the leading ``<style name>:`` restatement from a prompt."""
    raw = prompt.strip()
    if not raw:
        return raw

    # Exact name followed by a colon, allowing odd spaces around the colon.
    m = re.match(
        rf"^\s*{re.escape(name)}\s*[:：]\s*",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        return raw[m.end():].lstrip()

    # Fallback for names whose punctuation/diacritics differ from the sheet.
    target = _compact(name)
    if target:
        for m in re.finditer(r"[:：]", raw[: max(160, len(name) * 3)]):
            if _compact(raw[: m.start()]) == target:
                return raw[m.end():].lstrip()
    return raw


def strip_leading_restatement(name: str, prompt: str) -> str:
    """Drop a first comma-separated segment that only restates the name."""
    if "," not in prompt:
        return prompt
    first, rest = prompt.split(",", 1)
    first_norm = _norm_words(first).strip(" .,;:-–—")
    name_norm = _norm_words(name).strip(" .,;:-–—")
    if not first_norm or not name_norm:
        return prompt

    first_words = first_norm.split()
    name_words = name_norm.split()
    if first_words[: len(name_words)] == name_words:
        extra = len(first_words) - len(name_words)
        if 0 <= extra <= 6:
            return rest.lstrip(" \t,;:-–—")
    return prompt


def clean_prompt(name: str, raw: str) -> str:
    prompt = re.sub(r"[\r\n]+", " ", raw).strip()
    prompt = strip_name_prefix(name, prompt)
    prompt = strip_leading_restatement(name, prompt)
    prompt = re.sub(r"\s+", " ", prompt).strip(" \t,;:-–—")
    if prompt:
        return prompt
    # Never emit an empty prompt; fall back to the prefix-stripped text.
    fallback = re.sub(r"\s+", " ", strip_name_prefix(name, raw)).strip()
    return fallback or raw.strip()


def _prompt_key(prompt: str) -> str:
    return _norm_words(prompt)


def dedupe(records: list[dict]) -> tuple[list[dict], int, int]:
    """Collapse exact duplicate prompts and cross-name prefix near-duplicates."""
    exact_seen: set[tuple[str, str]] = set()
    kept: list[dict] = []
    exact_removed = 0
    for rec in records:
        key = (rec["name"].casefold(), _prompt_key(rec["prompt"]))
        if key in exact_seen:
            exact_removed += 1
            continue
        exact_seen.add(key)
        kept.append(rec)

    # If one style name is a word-prefix of another and the prompts are almost
    # identical, the longer name is a copy of the same concept. Keep the
    # shorter, more general name.
    prefix_removed = 0
    drop: set[int] = set()
    for i, a in enumerate(kept):
        a_name = match_key(a["name"]).strip()
        a_prompt = _prompt_key(a["prompt"])
        for j, b in enumerate(kept):
            if i == j or j in drop:
                continue
            b_name = match_key(b["name"]).strip()
            if not a_name or not b_name or a_name == b_name:
                continue
            if not b_name.startswith(a_name + " "):
                continue
            ratio = SequenceMatcher(None, a_prompt, _prompt_key(b["prompt"])).ratio()
            if ratio >= 0.9:
                drop.add(j)
                prefix_removed += 1

    if drop:
        kept = [rec for idx, rec in enumerate(kept) if idx not in drop]
    return kept, exact_removed, prefix_removed


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def fetch_text(url: str, timeout: float) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "ComfyUI-skkut-utils style importer "
                "(+https://github.com/skkut/ComfyUI-skkut-utils)"
            ),
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    return payload.decode("utf-8-sig")


def read_sheet(args: argparse.Namespace) -> str:
    if args.input:
        return Path(args.input).read_bytes().decode("utf-8-sig")
    return fetch_text(args.source_url, args.timeout)


def parse_sheet(text: str, min_rows: int) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None:
        raise ValueError("sheet is empty or not CSV")
    missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
    if missing:
        raise ValueError(f"sheet is missing required columns: {', '.join(missing)}")

    records: list[dict] = []
    for index, row in enumerate(reader, start=1):
        values = {column: (row.get(column) or "").strip() for column in REQUIRED_COLUMNS}
        if not any(values[column] for column in ("Style Name", "Wildcard Style", "Category")):
            continue
        name = values["Style Name"]
        raw_prompt = values["Wildcard Style"]
        category = values["Category"]
        if not name:
            raise ValueError(f"row {index} has no Style Name")
        if not raw_prompt:
            raise ValueError(f"row {index} ({name!r}) has no Wildcard Style prompt")
        if not category:
            raise ValueError(f"row {index} ({name!r}) has no Category")
        try:
            order = int(values["Order"])
        except ValueError:
            order = 10**9 + index
        records.append(
            {
                "order": order,
                "name": name,
                "raw_prompt": raw_prompt,
                "prompt": clean_prompt(name, raw_prompt),
                "category": category,
                "medium": values["Medium"],
                "family": values["Family / Subcategory"],
                "era": values["Era / Period"],
                "original_row": values["Original Row"],
            }
        )

    if len(records) < min_rows:
        raise ValueError(
            f"only {len(records)} data rows parsed; expected at least {min_rows}. "
            "The sheet may have failed to load or changed shape."
        )
    return records


def load_existing_names(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    styles = data.get("styles")
    if not isinstance(styles, list):
        raise ValueError(f"{path} has no styles list")
    names = set()
    for style in styles:
        name = style.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{path} contains a style without a name")
        names.add(name.casefold())
    return names


def load_rename_exclusions(path: Path) -> tuple[set[str], list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    exclusions = data.get("exclusions")
    if not isinstance(exclusions, list):
        raise ValueError(f"{path} has no exclusions list")
    names: set[str] = set()
    for entry in exclusions:
        if not isinstance(entry, dict) or not isinstance(entry.get("new"), str):
            raise ValueError(f"{path} has an invalid exclusion entry")
        names.add(entry["new"].casefold())
    return names, exclusions


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build_styles(args: argparse.Namespace) -> tuple[dict, dict]:
    text = read_sheet(args)
    records = parse_sheet(text, args.min_rows)

    existing_names = load_existing_names(Path(args.existing))
    rename_names, rename_entries = load_rename_exclusions(Path(args.renames))

    # Validate the curated mapping before using it, so a typo fails CI rather
    # than silently over- or under-filtering.
    sheet_names = {rec["name"].casefold() for rec in records}
    errors = []
    for entry in rename_entries:
        if entry["new"].casefold() not in sheet_names:
            errors.append(f"rename exclusion not found in sheet: {entry['new']!r}")
        for old in entry.get("existing", []):
            if not isinstance(old, str):
                errors.append(f"invalid existing name in exclusion for {entry['new']!r}")
            elif old.casefold() not in existing_names:
                errors.append(
                    f"rename exclusion references unknown existing style: {old!r} "
                    f"(for {entry['new']!r})"
                )
    if errors:
        raise ValueError("invalid rename mapping:\n  " + "\n  ".join(errors))

    kept, exact_removed, prefix_removed = dedupe(records)

    excluded_existing = 0
    excluded_renamed = 0
    selected: list[dict] = []
    for rec in kept:
        key = rec["name"].casefold()
        if key in existing_names:
            excluded_existing += 1
            continue
        if key in rename_names:
            excluded_renamed += 1
            continue
        rec["section"] = assign_section(rec["name"], rec["category"], rec["medium"])
        selected.append(rec)

    # Disambiguate any remaining duplicate names with " (2)", " (3)", ...
    # Names are assigned before suffixing so exclusions stay exact.
    used = {name.casefold() for name in existing_names}
    counts: Counter[str] = Counter()
    for rec in sorted(selected, key=lambda r: (r["order"], r["name"].casefold())):
        base = rec["name"]
        key = base.casefold()
        counts[key] += 1
        occurrence = counts[key]
        if occurrence == 1 and key not in used:
            rec["output_name"] = base
        else:
            suffix = max(2, occurrence)
            candidate = f"{base} ({suffix})"
            while candidate.casefold() in used:
                suffix += 1
                candidate = f"{base} ({suffix})"
            rec["output_name"] = candidate
        used.add(rec["output_name"].casefold())

    section_index = {name: idx for idx, name in enumerate(SECTION_ORDER)}
    selected.sort(
        key=lambda r: (
            section_index[r["section"]],
            r["order"],
            r["output_name"].casefold(),
        )
    )

    styles = []
    for rec in selected:
        section = rec["section"]
        negative = SECTION_NEGATIVES[section]
        styles.append(
            {
                "name": rec["output_name"],
                "section": section,
                "source": SOURCE_NAME,
                "prompt": rec["prompt"],
                "negative": negative,
                "template": None,
                "thumb": None,
            }
        )

    used_sections = [section for section in SECTION_ORDER if any(
        style["section"] == section for style in styles
    )]
    data = {
        "version": 1,
        "credits": {
            "style_texts": (
                "Style descriptions are from the Classified_Styles sheet compiled and "
                "shared publicly by u/Dear-Spend-2865 (Reddit). No license is stated "
                "for the sheet; these texts are not MIT and are bundled here with "
                "attribution only."
            ),
            "source": (
                "https://docs.google.com/spreadsheets/d/"
                "1fb2yD74gqT_BxmBpkOMX2V7gSj_A8RQ0/ "
                "(sheet title: styles_wildcard_v18_krea2_classified; "
                "Classified_Styles tab)"
            ),
            "cleaning": (
                "The leading '<style name>:' prefix and any short leading restatement "
                "of the style name were removed from each prompt; wording is otherwise "
                "unchanged."
            ),
            "filtering": (
                "Rows whose name already exists in skutils_style_selector/styles.json "
                "and rows listed as renamed or reworked counterparts in "
                "scripts/classified_styles_v18_renames.json are omitted. Exact duplicate "
                "prompts and one cross-name prefix near-duplicate were collapsed."
            ),
            "sections": (
                "Sheet categories were mapped to the bundled library's sections. Two "
                "sections were added for genuinely new sheet groupings: Illustration and "
                "Character & Creature Design. Emotion and Edit have no sheet styles."
            ),
            "negatives": (
                "Every style carries a section-level baseline negative prompt generated "
                "by the importer; negatives are not individually curated per style."
            ),
            "generator": "scripts/import_classified_styles.py",
        },
        "sections": used_sections,
        "styles": styles,
    }
    stats = {
        "sheet_rows": len(records),
        "duplicate_rows_removed": exact_removed + prefix_removed,
        "exact_duplicates_removed": exact_removed,
        "prefix_duplicates_removed": prefix_removed,
        "existing_name_rows_removed": excluded_existing,
        "renamed_rows_removed": excluded_renamed,
        "styles": len(styles),
        "sections": len(used_sections),
        "exclusion_groups": len(rename_entries),
    }
    return data, stats


def validate_output(data: dict, existing_names: set[str]) -> None:
    styles = data["styles"]
    if not styles:
        raise ValueError("output has no styles")
    names: set[str] = set()
    allowed_sections = set(SECTION_ORDER)
    for style in styles:
        name = style["name"]
        if not name or not name.strip():
            raise ValueError("output style has an empty name")
        key = name.casefold()
        if key in names:
            raise ValueError(f"duplicate output style name: {name!r}")
        if key in existing_names:
            raise ValueError(f"output style collides with existing library: {name!r}")
        names.add(key)
        if style["section"] not in allowed_sections:
            raise ValueError(f"unknown output section: {style['section']!r}")
        if not style["prompt"].strip():
            raise ValueError(f"empty prompt for {name!r}")
        if not style["negative"].strip():
            raise ValueError(f"empty negative for {name!r}")
        if style["source"] != SOURCE_NAME:
            raise ValueError(f"wrong source for {name!r}: {style['source']!r}")
        if style["template"] is not None or style["thumb"] is not None:
            raise ValueError(f"unexpected template/thumb for {name!r}")
    if data["sections"] != [s for s in SECTION_ORDER if s in {x["section"] for x in styles}]:
        raise ValueError("sections list does not match used sections in order")


def write_output(path: Path, data: dict) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return text


def check_output(path: Path, expected: str) -> int:
    if not path.exists():
        print(f"error: {path} does not exist; run without --check to create it", file=sys.stderr)
        return 1
    actual = path.read_text(encoding="utf-8")
    if actual == expected:
        return 0
    diff = list(
        unified_diff(
            actual.splitlines(),
            expected.splitlines(),
            fromfile=str(path),
            tofile="generated",
            lineterm="",
            n=2,
        )
    )
    print("error: generated output does not match the committed file", file=sys.stderr)
    for line in diff[:80]:
        print(line, file=sys.stderr)
    if len(diff) > 80:
        print(f"... {len(diff) - 80} more diff lines", file=sys.stderr)
    return 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import the Classified_Styles sheet into the curated Skutils style "
            "file. Never writes skutils_style_selector/styles.json."
        )
    )
    parser.add_argument(
        "--input",
        help="local CSV to read instead of downloading the live sheet",
    )
    parser.add_argument(
        "--source-url",
        default=SOURCE_URL,
        help="published CSV endpoint (default: the Classified_Styles gviz CSV)",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="output JSON path (default: scripts/classified_styles_v18_curated.json)",
    )
    parser.add_argument(
        "--renames",
        default=str(DEFAULT_RENAMES),
        help="curated rename-exclusion JSON",
    )
    parser.add_argument(
        "--existing",
        default=str(DEFAULT_EXISTING),
        help="bundled library used for exact-name exclusions",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare generated output with the committed file; do not write",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds for the live sheet (default: 60)",
    )
    parser.add_argument(
        "--min-rows",
        type=int,
        default=1200,
        help="fail if fewer than this many data rows are parsed (default: 1200)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        data, stats = build_styles(args)
        existing_names = load_existing_names(Path(args.existing))
        validate_output(data, existing_names)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    generated = json.dumps(data, ensure_ascii=False, indent=2) + "\n"

    print(
        "sheet rows: {sheet_rows} | duplicates removed: {duplicate_rows_removed} "
        "({exact_duplicates_removed} exact, {prefix_duplicates_removed} prefix) | "
        "existing names removed: {existing_name_rows_removed} | "
        "renamed counterparts removed: {renamed_rows_removed} | "
        "styles: {styles} | sections: {sections}".format(**stats)
    )

    if args.check:
        return check_output(output_path, generated)

    write_output(output_path, data)
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
