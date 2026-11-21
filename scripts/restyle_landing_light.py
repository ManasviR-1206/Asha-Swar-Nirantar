"""Phase 10 — flip the landing page's content sections to the light
healthcare surface.

The 3D hero and the final CTA stay dark; every section in between becomes
warm ivory with white cards and deep-slate text.
"""
import io
import re

PATH = "frontend/src/pages/Landing.jsx"
src = io.open(PATH, encoding="utf-8").read()
before = src

# ---- headings: default colour follows the surface ----------------------
# The hero heading (line ~311) and the FinalCTA heading (line ~803) keep
# their light colour, so they are protected by splitting the file.
hero_start = src.index('className="text-4xl sm:text-5xl lg:text-[3.4rem] font-extrabold')
cta_start = src.index('<h2 className="text-3xl sm:text-5xl font-extrabold mt-6 leading-tight">')

head = src[:cta_start]
tail = src[cta_start:]

# Headings in the light sections -> deep slate.
head = head.replace(
    '<h2 className="text-3xl sm:text-4xl font-extrabold">',
    '<h2 className="text-3xl sm:text-4xl font-extrabold text-teal-deep">',
)
head = head.replace(
    '<h2 className="text-3xl sm:text-4xl font-extrabold leading-tight">',
    '<h2 className="text-3xl sm:text-4xl font-extrabold leading-tight text-teal-deep">',
)
head = head.replace(
    '<h3 className="font-bold text-lg mb-2.5">{title}</h3>',
    '<h3 className="font-bold text-lg mb-2.5 text-teal-deep">{title}</h3>',
)
head = head.replace(
    '<h3 className="font-extrabold tracking-[0.2em] text-sm mb-3">{s.title}</h3>',
    '<h3 className="font-extrabold tracking-[0.2em] text-sm mb-3 text-teal-deep">{s.title}</h3>',
)
head = head.replace(
    '<h3 className="font-bold">{f.title}</h3>',
    '<h3 className="font-bold text-teal-deep">{f.title}</h3>',
)

# ---- body copy -----------------------------------------------------------
head = head.replace('text-[#c9d3d7]/80', 'text-teal-deep/60')
head = head.replace('text-[#c9d3d7]/85', 'text-teal-deep/65')
head = head.replace('text-[#c9d3d7]/75', 'text-teal-deep/55')
head = head.replace('text-[#c9d3d7]', 'text-teal-deep/60')

# The "pitch" panel is a light card now.
head = head.replace(
    '<motion.div {...fadeUp} className="mt-10 glass rounded-3xl p-8 text-center">\n'
    '          <p className="text-white/85 text-lg font-semibold max-w-3xl mx-auto leading-relaxed">',
    '<motion.div\n'
    '            {...fadeUp}\n'
    '            className="mt-10 card-ivory rounded-3xl p-8 text-center"\n'
    '          >\n'
    '          <p className="text-teal-deep/80 text-lg font-semibold max-w-3xl mx-auto leading-relaxed">',
)
head = head.replace(
    '<span className="text-white/50">{t("ld.pitch2", "what was said")}</span>.{" "}',
    '<span className="text-teal-deep/45">{t("ld.pitch2", "what was said")}</span>.{" "}',
)
head = head.replace(
    'text-[5rem] font-black text-white/[0.045]',
    'text-[5rem] font-black text-teal-deep/[0.05]',
)

# ---- cards ---------------------------------------------------------------
# Feature / step / benefit cards: white surface with a soft border.
head = head.replace(
    '<motion.div {...fadeUp} className="glass rounded-3xl p-7 hover:border-pink/40 transition-colors group">',
    '<motion.div\n'
    '          {...fadeUp}\n'
    '          className="card-ivory rounded-3xl p-7 hover:border-pink/45 transition-colors group"\n'
    '        >',
)
head = head.replace(
    '<div className="glass rounded-[2rem] p-8 sm:p-12">',
    '<div className="card-ivory rounded-[2rem] p-8 sm:p-12">',
)
head = head.replace(
    '<div className="glass rounded-3xl p-7 relative overflow-hidden">',
    '<div className="card-ivory rounded-3xl p-7 relative overflow-hidden">',
)
head = head.replace(
    '<div key={it.title} className="glass rounded-2xl p-5">',
    '<div key={it.title} className="card-ivory rounded-2xl p-5">',
)
head = head.replace(
    '<div className="glass rounded-[2rem] p-8 sm:p-10 relative overflow-hidden">',
    '<div className="card-ivory rounded-[2rem] p-8 sm:p-10 relative overflow-hidden">',
)
head = head.replace(
    'className="w-[72px] h-[72px] mx-auto rounded-full glass flex items-center justify-center mb-5 relative z-10 bg-bg-base/60"',
    'className="w-[72px] h-[72px] mx-auto rounded-full flex items-center justify-center mb-5 relative z-10 bg-blush/15"',
)

# The small tinted panels inside the benefit cards were dark glass on a
# dark page; on the light surface they become soft blush panels.
head = head.replace(
    '<div className="glass-strong rounded-2xl p-5 flex items-start gap-4">',
    '<div className="rounded-2xl bg-blush/15 p-5 flex items-start gap-4">',
)
head = head.replace(
    'className="glass-strong rounded-2xl p-5 flex items-start gap-4"',
    'className="rounded-2xl bg-blush/15 p-5 flex items-start gap-4"',
)

src = head + tail

# ---- final CTA + footer (still dark) -------------------------------------
src = src.replace(
    'background:\n'
    '            "linear-gradient(140deg, rgba(232,77,155,0.16), rgba(135,85,217,0.12)), '
    'linear-gradient(160deg, #3a2b33, #2f3d44)",\n'
    '          border: "1px solid rgba(240,120,173,0.28)",',
    'background:\n'
    '            "linear-gradient(140deg, rgba(232,168,184,0.24), rgba(168,200,181,0.16)), '
    'linear-gradient(160deg, #98566c, #34434a)",\n'
    '          border: "1px solid rgba(232,168,184,0.4)",',
)
src = src.replace(
    'background: "radial-gradient(600px 300px at 50% 0%, rgba(232,77,155,0.14), transparent)",',
    'background: "radial-gradient(600px 300px at 50% 0%, rgba(232,168,184,0.2), transparent)",',
)
src = src.replace(
    '<p className="text-[#c9d3d7]/85 mt-5 max-w-xl mx-auto text-sm sm:text-base">',
    '<p className="text-white/75 mt-5 max-w-xl mx-auto text-sm sm:text-base">',
)

# Footer: light strip with slate text.
src = src.replace(
    '<footer className="border-t border-white/5 py-10">\n'
    '      <div className="max-w-7xl mx-auto px-5 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-white/40">',
    '<footer className="border-t border-blush/25 bg-white/60 py-10">\n'
    '      <div className="max-w-7xl mx-auto px-5 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-teal-deep/50">',
)
src = src.replace(
    '<span className="font-bold text-white/70">{t("app.name")}</span>',
    '<span className="font-bold text-teal-deep/80">{t("app.name")}</span>',
)

io.open(PATH, "w", encoding="utf-8").write(src)
print("landing light-section restyle applied:", len(before), "->", len(src))
