"""Phase 10 — restructure the landing page for the blush-pink healthcare
identity.

* The 3D hero keeps a dark, calm backdrop (deep slate tinted with rose) so
  the holographic characters stay readable.
* Every content section below the hero becomes a light surface: warm ivory
  page, white cards, deep slate text.
* The final CTA stays a rich rose focal point.
"""
import io

PATH = "frontend/src/pages/Landing.jsx"
src = io.open(PATH, encoding="utf-8").read()
original = src


def rep(old, new, count=1):
    global src
    if old not in src:
        raise SystemExit(f"PATTERN NOT FOUND:\n{old[:200]}")
    src = src.replace(old, new, count)


# ---------------------------------------------------------------- orb
rep(
    'background: "radial-gradient(circle at 35% 35%, #ffd3e6, #e8a8b8 55%, #98566c)",\n'
    '        boxShadow: "0 0 12px rgba(240,120,173,0.85), 0 0 34px rgba(187,166,255,0.4)",',
    'background: "radial-gradient(circle at 35% 35%, #f6dce3, #e8a8b8 55%, #98566c)",\n'
    '        boxShadow: "0 0 12px rgba(232,168,184,0.85), 0 0 34px rgba(168,200,181,0.4)",',
)

# ---------------------------------------------------------------- nav
# The nav sits over the dark hero at the top and over the light sections
# once the user scrolls, so it switches to a light surface when scrolled.
rep(
    'className={`fixed top-0 inset-x-0 z-50 transition-all duration-300 bg-[#2f3d44]/35 '
    'backdrop-blur-md border-b border-white/5 ${\n'
    '        scrolled ? "bg-[#2f3d44]/60 shadow-glass" : ""\n'
    '      }`}',
    'className={`fixed top-0 inset-x-0 z-50 transition-all duration-300 '
    'backdrop-blur-md border-b ${\n'
    '        scrolled\n'
    '          ? "bg-white/85 border-blush/25 shadow-soft"\n'
    '          : "bg-[#2f3d44]/35 border-white/10"\n'
    '      }`}',
)
rep(
    '<div className="font-extrabold tracking-wide text-[15px]">{t("app.name")}</div>\n'
    '            <div className="text-[10px] text-pink/80 tracking-[0.18em] uppercase">{t("app.tagline")}</div>',
    '<div\n'
    '              className={`font-extrabold tracking-wide text-[15px] ${\n'
    '                scrolled ? "text-teal-deep" : "text-white"\n'
    '              }`}\n'
    '            >\n'
    '              {t("app.name")}\n'
    '            </div>\n'
    '            <div className="text-[10px] text-pink tracking-[0.18em] uppercase">\n'
    '              {t("app.tagline")}\n'
    '            </div>',
)
rep(
    '<div className="hidden md:flex items-center gap-7 text-sm text-white/80">\n'
    '          {links.map(([label, href]) => (\n'
    '            <a key={href} href={href} className="whitespace-nowrap hover:text-pink transition-colors">',
    '<div\n'
    '          className={`hidden md:flex items-center gap-7 text-sm ${\n'
    '            scrolled ? "text-teal-deep/75" : "text-white/80"\n'
    '          }`}\n'
    '        >\n'
    '          {links.map(([label, href]) => (\n'
    '            <a\n'
    '              key={href}\n'
    '              href={href}\n'
    '              className="whitespace-nowrap hover:text-pink transition-colors"\n'
    '            >',
)
rep(
    '<LanguagePicker lang={lang} setLang={setLang} tone="dark" />\n'
    '          <Link to="/login" className="btn-mint px-5 py-2 text-sm">',
    '<LanguagePicker lang={lang} setLang={setLang} tone={scrolled ? "light" : "dark"} />\n'
    '          <Link to="/login" className="btn-mint px-5 py-2 text-sm">',
)
rep(
    '<button\n          className="md:hidden text-white/90"',
    '<button\n          className={`md:hidden ${scrolled ? "text-teal-deep" : "text-white/90"}`}',
)
rep(
    '<span className={`block w-6 h-0.5 bg-white transition ${open ? "rotate-45 translate-y-2" : ""}`} />\n'
    '            <span className={`block w-6 h-0.5 bg-white transition ${open ? "opacity-0" : ""}`} />\n'
    '            <span className={`block w-6 h-0.5 bg-white transition ${open ? "-rotate-45 -translate-y-2" : ""}`} />',
    '<span\n'
    '              className={`block w-6 h-0.5 transition ${\n'
    '                scrolled ? "bg-teal-deep" : "bg-white",\n'
    '                open ? "rotate-45 translate-y-2" : ""\n'
    '              }`}\n'
    '            />\n'
    '            <span\n'
    '              className={`block w-6 h-0.5 transition ${\n'
    '                scrolled ? "bg-teal-deep" : "bg-white",\n'
    '                open ? "opacity-0" : ""\n'
    '              }`}\n'
    '            />\n'
    '            <span\n'
    '              className={`block w-6 h-0.5 transition ${\n'
    '                scrolled ? "bg-teal-deep" : "bg-white",\n'
    '                open ? "-rotate-45 -translate-y-2" : ""\n'
    '              }`}\n'
    '            />',
)

# ---------------------------------------------------------------- hero ground
# The 3D canvas is transparent; the section supplies the dark ground.
rep(
    '<section id="home" className="relative min-h-screen overflow-hidden">\n'
    '      {/* full-bleed immersive 3D world */}',
    '<section\n'
    '      id="home"\n'
    '      className="relative min-h-screen overflow-hidden"\n'
    '      style={{\n'
    '        background:\n'
    '          "radial-gradient(120% 90% at 78% 18%, #4a5a5f 0%, #2f3d44 45%, #263238 100%)",\n'
    '      }}\n'
    '    >\n'
    '      {/* full-bleed immersive 3D world */}',
)
# the left legibility scrim and the bottom fade
rep(
    '"linear-gradient(90deg, rgba(16,12,24,0.72) 0%, rgba(16,12,24,0.38) 48%, rgba(16,12,24,0) 100%)",',
    '"linear-gradient(90deg, rgba(30,40,44,0.82) 0%, rgba(30,40,44,0.45) 48%, rgba(30,40,44,0) 100%)",',
)
rep(
    '"linear-gradient(180deg, rgba(16,12,24,0) 0%, rgba(16,12,24,0.85) 100%)",',
    '"linear-gradient(180deg, rgba(38,50,56,0) 0%, rgba(38,50,56,0.92) 78%, #fff8f6 100%)",',
)
# the hero headline + copy sit on the dark ground, so they stay light
rep(
    'className="mt-4 text-[#c9d3d7] text-sm sm:text-base max-w-md leading-relaxed"',
    'className="mt-4 text-white/70 text-sm sm:text-base max-w-md leading-relaxed"',
)
rep(
    '<a href="#features" className="btn-ghost px-7 py-3.5 text-sm inline-flex items-center gap-2 glass">',
    '<a\n'
    '              href="#features"\n'
    '              className="btn-ghost px-7 py-3.5 text-sm inline-flex items-center gap-2 !border-white/30 !text-white hover:!bg-white/10"\n'
    '            >',
)
rep(
    'className="mt-8 hidden sm:flex items-center gap-5 text-[11px] tracking-[0.14em] uppercase text-white/45"',
    'className="mt-8 hidden sm:flex items-center gap-5 text-[11px] tracking-[0.14em] uppercase text-white/55"',
)
rep(
    '<p className="hidden sm:block text-[10px] text-white/35 max-w-[210px] leading-snug">',
    '<p className="hidden sm:block text-[10px] text-white/45 max-w-[210px] leading-snug">',
)
rep(
    '<p className="hidden sm:block text-[10px] text-white/25 max-w-[210px] leading-snug text-right">',
    '<p className="hidden sm:block text-[10px] text-white/35 max-w-[210px] leading-snug text-right">',
)

# ---------------------------------------------------------------- sections
# SectionBackdrop: the sections now sit on the warm-ivory page.
rep(
    'style={{\n'
    '        background:\n'
    '          "linear-gradient(180deg, rgba(33,19,41,0.0) 0%, rgba(33,19,41,0.9) 12%, rgba(33,19,41,0.9) 88%, rgba(33,19,41,0.0) 100%)",\n'
    '      }}',
    'style={{\n'
    '        background:\n'
    '          "linear-gradient(180deg, rgba(255,248,246,0) 0%, rgba(255,248,246,1) 10%, rgba(255,248,246,1) 90%, rgba(255,248,246,0) 100%)",\n'
    '      }}',
)

io.open(PATH, "w", encoding="utf-8").write(src)
print("landing.jsx restructured:", len(original), "->", len(src))
