/**
 * tobkiri visual direction: 「風景の余韻」— contemporary Japanese editorialism.
 * This page uses asymmetry, paper-like surfaces, charcoal depth and vermilion-earth accents.
 */
import { motion, useScroll, useSpring } from "framer-motion";
import { ArrowDownRight, ArrowUpRight, Menu, X } from "lucide-react";
import { useEffect, useState } from "react";

const heroImage = "/manus-storage/tobkiri-hero-landscape_894eeec2.jpg";
const markImage = "/manus-storage/tobkiri-mark_4a751b24.png";

const works = [
  {
    number: "01",
    category: "OBJECTS / 2026",
    title: "手ざわりから、\n風景をひらく。",
    description: "日々の動作に、ひとつの余白を添えるもの。素材の気配を、静かなかたちにしています。",
    image: "/manus-storage/tobkiri-work-still-life_ebaca1a5.jpg",
    orientation: "landscape",
  },
  {
    number: "02",
    category: "PLACES / 2026",
    title: "境界を越える、\n小さな入口。",
    description: "土地の記憶と、これからの時間が出会う場所。通り過ぎるだけではない、滞在の景色を考えます。",
    image: "/manus-storage/tobkiri-work-architecture_4bf1f993.jpg",
    orientation: "portrait",
  },
  {
    number: "03",
    category: "MOMENTS / ONGOING",
    title: "名前のない気分を、\n記憶に残す。",
    description: "光、風、会話。すぐに消えてしまう感覚を、そっとすくいあげるための編集を続けています。",
    image: "/manus-storage/tobkiri-work-motion_65952c9e.jpg",
    orientation: "portrait",
  },
];

const fadeUp = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0 },
};

function scrollToSection(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export default function Home() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);
  const { scrollYProgress } = useScroll();
  const progressScale = useSpring(scrollYProgress, { stiffness: 130, damping: 28, mass: 0.25 });

  useEffect(() => {
    const onScroll = () => setIsScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const closeAndScroll = (id: string) => {
    setIsMenuOpen(false);
    window.setTimeout(() => scrollToSection(id), 80);
  };

  return (
    <div className="site-shell">
      <motion.div className="progress-line" style={{ scaleX: progressScale }} />

      <header className={`site-header ${isScrolled ? "site-header--scrolled" : ""}`}>
        <a className="brand-lockup" href="#top" aria-label="tobkiri トップへ" onClick={() => scrollToSection("top")}>
          <img src={markImage} alt="" className="brand-mark" />
          <span>tobkiri</span>
        </a>
        <nav className="desktop-nav" aria-label="主なナビゲーション">
          <button type="button" onClick={() => scrollToSection("about")}>ABOUT</button>
          <button type="button" onClick={() => scrollToSection("editions")}>EDITIONS</button>
          <button type="button" onClick={() => scrollToSection("contact")}>CONTACT</button>
        </nav>
        <button
          className="menu-toggle"
          type="button"
          aria-label={isMenuOpen ? "メニューを閉じる" : "メニューを開く"}
          aria-expanded={isMenuOpen}
          onClick={() => setIsMenuOpen((open) => !open)}
        >
          {isMenuOpen ? <X size={21} strokeWidth={1.6} /> : <Menu size={22} strokeWidth={1.6} />}
        </button>
      </header>

      <div className={`mobile-menu ${isMenuOpen ? "mobile-menu--open" : ""}`} aria-hidden={!isMenuOpen}>
        <button type="button" onClick={() => closeAndScroll("about")}>ABOUT <ArrowUpRight size={20} /></button>
        <button type="button" onClick={() => closeAndScroll("editions")}>EDITIONS <ArrowUpRight size={20} /></button>
        <button type="button" onClick={() => closeAndScroll("contact")}>CONTACT <ArrowUpRight size={20} /></button>
      </div>

      <main id="top">
        <section className="hero" aria-labelledby="hero-heading">
          <div className="hero-image-wrap">
            <img className="hero-image" src={heroImage} alt="夕暮れの海と、静かな岩の風景" />
            <div className="hero-vignette" />
          </div>
          <div className="hero-grid" aria-hidden="true" />
          <motion.p className="hero-kicker" initial="hidden" animate="visible" variants={fadeUp} transition={{ duration: 0.7, delay: 0.25 }}>
            A SENSE-MAKING ATELIER<br />
            TOKYO · JAPAN
          </motion.p>
          <motion.h1 id="hero-heading" className="hero-title" initial="hidden" animate="visible" variants={fadeUp} transition={{ duration: 0.9, delay: 0.38 }}>
            <span>まだ言葉にならない、</span>
            <em>好きの輪郭へ。</em>
          </motion.h1>
          <motion.div className="hero-foot" initial="hidden" animate="visible" variants={fadeUp} transition={{ duration: 0.7, delay: 0.55 }}>
            <p>暮らしのなかの小さな発見を、<br />とびきりの記憶へと編集する。</p>
            <button className="circle-action circle-action--light" type="button" onClick={() => scrollToSection("about")} aria-label="tobkiri について読む">
              <ArrowDownRight size={24} strokeWidth={1.4} />
            </button>
          </motion.div>
          <span className="hero-side-note">SCROLL TO NOTICE</span>
        </section>

        <section id="about" className="intro-section section-pad">
          <div className="section-index">01 <span>ORIGIN</span></div>
          <motion.div className="intro-copy" initial="hidden" whileInView="visible" viewport={{ once: true, amount: 0.32 }} variants={fadeUp} transition={{ duration: 0.7 }}>
            <p className="eyebrow">THE QUIET EXTRAORDINARY</p>
            <h2>いい一日は、<br /><em>少しの発見</em>からはじまる。</h2>
            <p className="body-copy">tobkiri は、日常のなかに潜む豊かさを見つめるための感性のアトリエです。もの、場所、時間。その輪郭を丁寧に見つけ、心に残る体験へと編みなおしていきます。</p>
            <button className="text-action" type="button" onClick={() => scrollToSection("editions")}>
              EDITIONS を見る <span><ArrowUpRight size={17} strokeWidth={1.8} /></span>
            </button>
          </motion.div>
          <div className="intro-aside" aria-hidden="true">
            <span>tobkiri is a pause<br />that opens a view.</span>
          </div>
        </section>

        <section id="editions" className="editions-section">
          <div className="editions-heading section-pad">
            <div className="section-index section-index--light">02 <span>EDITIONS</span></div>
            <motion.div initial="hidden" whileInView="visible" viewport={{ once: true, amount: 0.5 }} variants={fadeUp} transition={{ duration: 0.65 }}>
              <p className="eyebrow eyebrow--light">THINGS WORTH NOTICING</p>
              <h2>景色を、<em>ひとつずつ。</em></h2>
            </motion.div>
          </div>
          <div className="edition-list">
            {works.map((work, index) => (
              <motion.article
                className={`edition-card edition-card--${work.orientation}`}
                key={work.number}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true, amount: 0.18 }}
                variants={fadeUp}
                transition={{ duration: 0.7, delay: index * 0.07 }}
              >
                <div className="edition-image-wrap">
                  <img src={work.image} alt="" className="edition-image" />
                  <span className="image-corner" />
                </div>
                <div className="edition-info">
                  <p><span>{work.number}</span>{work.category}</p>
                  <h3>{work.title.split("\n").map((line) => <span key={line}>{line}</span>)}</h3>
                  <div className="edition-meta">
                    <span>{work.description}</span>
                    <button className="circle-action" type="button" onClick={() => scrollToSection("contact")} aria-label={`${work.category}について問い合わせる`}><ArrowUpRight size={20} strokeWidth={1.5} /></button>
                  </div>
                </div>
              </motion.article>
            ))}
          </div>
        </section>

        <section className="manifesto-section section-pad">
          <div className="section-index">03 <span>MANIFESTO</span></div>
          <motion.div className="manifesto-copy" initial="hidden" whileInView="visible" viewport={{ once: true, amount: 0.3 }} variants={fadeUp} transition={{ duration: 0.8 }}>
            <p>美しさは、遠くにある特別なものではなく、<br className="desktop-break" />気づくための余白から生まれる。</p>
            <span>— tobkiri, a small note on everyday wonder</span>
          </motion.div>
          <div className="manifesto-orbit" aria-hidden="true"><i /><i /><i /></div>
        </section>

        <section id="contact" className="contact-section">
          <div className="contact-topline"><span>04</span><span>AN INVITATION</span><span>2026</span></div>
          <motion.div className="contact-content" initial="hidden" whileInView="visible" viewport={{ once: true, amount: 0.4 }} variants={fadeUp} transition={{ duration: 0.8 }}>
            <p className="eyebrow">LET'S NOTICE SOMETHING NEW</p>
            <h2>次の景色を、<br /><em>ひらく。</em></h2>
            <a className="contact-link" href="mailto:hello@tobkiri.jp">
              <span>HELLO@TOBKIRI.JP</span>
              <ArrowUpRight size={26} strokeWidth={1.45} />
            </a>
          </motion.div>
          <div className="contact-mark"><img src={markImage} alt="" /></div>
        </section>
      </main>

      <footer className="site-footer">
        <a className="brand-lockup" href="#top" onClick={() => scrollToSection("top")}>
          <img src={markImage} alt="" className="brand-mark" />
          <span>tobkiri</span>
        </a>
        <p>© 2026 TOBKIRI. THE QUIET EXTRAORDINARY.</p>
        <a href="#top" className="back-to-top" onClick={() => scrollToSection("top")}>BACK TO TOP <ArrowUpRight size={14} /></a>
      </footer>
    </div>
  );
}
