import { useState, useEffect } from "react";
import {
  X,
  BookOpen,
  Instagram,
  Cookie,
  ChevronLeft,
  ChevronRight,
  ImageIcon,
  ExternalLink,
  AlertTriangle,
  Info,
  MousePointerClick,
  Bot,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type GuideTab = "accounts" | "sessions" | "scrapingbot";

interface StepDef {
  title: string;
  description: string;
  img: string;
  note?: {
    type: "warning" | "info";
    text: string;
    link?: { label: string; href: string };
  };
  /** If true, the Next/Done button becomes a prominent CTA "Import Cookies ↗" */
  isCta?: boolean;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  initialTab?: GuideTab;
  /** Called when user clicks the Import Cookies CTA on the final step */
  onOpenCookieImport?: () => void;
}

// ---------------------------------------------------------------------------
// Step definitions
// ---------------------------------------------------------------------------

const STEPS_ACCOUNTS: StepDef[] = [
  {
    title: "Buka halaman IG Accounts",
    description:
      'Buka Settings → Instagram → IG Accounts. Klik tombol "Add Account" untuk menambah akun baru.',
    img: "/guide/1.png",
  },
  {
    title: "Isi data akun Instagram",
    description:
      "Masukkan username dan password akun Instagram yang akan digunakan untuk scraping, lalu klik Tambah.",
    img: "/guide/2.png",
    note: {
      type: "warning",
      text: "Server tidak bisa login langsung karena IP-nya diblok Instagram. Kita perlu import cookies dari browser setelah akun dibuat.",
    },
  },
  {
    title: "Install Cookie-Editor extension",
    description:
      'Install ekstensi Cookie-Editor dari Chrome Web Store dengan klik "Add to Chrome".',
    img: "/guide/3.png",
    note: {
      type: "info",
      text: "Install Cookie-Editor dari Chrome Web Store:",
      link: {
        label: "Cookie-Editor — Chrome Web Store",
        href: "https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm",
      },
    },
  },
  {
    title: "Pin Cookie-Editor ke toolbar",
    description:
      "Klik icon puzzle/ekstensi di Chrome (1), lalu klik pin di samping Cookie-Editor (2) agar mudah diakses dari toolbar.",
    img: "/guide/4.png",
  },
  {
    title: "Buka instagram.com dan login",
    description:
      "Buka instagram.com di browser yang sama, lalu login dengan akun yang sudah kamu tambahkan di app.",
    img: "/guide/5.png",
  },
  {
    title: "Beri izin Cookie-Editor",
    description:
      'Klik icon Cookie-Editor di toolbar (1), lalu pilih "This site" (2) untuk memberi akses ke cookies instagram.com.',
    img: "/guide/6.png",
  },
  {
    title: "Export cookies sebagai JSON",
    description:
      "Klik Export (1), pilih format All (2), lalu klik Export (3). Cookies akan otomatis ter-copy ke clipboard.",
    img: "/guide/7.png",
  },
  {
    title: "Pastikan sudah login ke akun yang benar",
    description:
      "Pastikan instagram.com terbuka dengan akun yang sama yang kamu daftarkan di app. Klik icon Cookie-Editor di toolbar (1), klik Export (2), lalu pilih format JSON (3) untuk menyalin cookies akun ini.",
    img: "/guide/8.png",
    note: {
      type: "warning",
      text: "Penting: pastikan kamu login sebagai akun yang sudah kamu tambahkan di app — bukan akun Instagram pribadi.",
    },
  },
  {
    title: "Modal Import Cookies terbuka",
    description:
      "Modal Import Cookies akan terbuka. Kamu akan diminta untuk paste hasil export Cookie-Editor tadi ke kolom yang tersedia.",
    img: "/guide/9.png",
  },
  {
    title: "Paste JSON cookies",
    description:
      "Paste hasil export Cookie-Editor (Ctrl+V) ke kolom JSON yang tersedia (1), lalu klik tombol Save/Import (2).",
    img: "/guide/10.png",
  },
  {
    title: "Selesai! Akun siap digunakan",
    description:
      "Pastikan JSON sudah ter-paste di kolom (1), lalu klik tombol Import (2) untuk menyimpan — akun akan langsung aktif dan siap scraping.",
    img: "/guide/11.png",
    isCta: true,
  },
];

const STEPS_SESSIONS: StepDef[] = [
  {
    title: "Install Cookie-Editor extension",
    description:
      "Sessions hanya butuh nilai sessionid cookie. Cara paling mudah mendapatkannya adalah via Cookie-Editor extension.",
    img: "/guide/3.png",
    note: {
      type: "info",
      text: "Install Cookie-Editor dari Chrome Web Store:",
      link: {
        label: "Cookie-Editor — Chrome Web Store",
        href: "https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm",
      },
    },
  },
  {
    title: "Buka instagram.com dan login",
    description:
      "Buka instagram.com di browser dan login dengan akun Instagram yang ingin kamu gunakan untuk scraping.",
    img: "/guide/5.png",
  },
  {
    title: "Beri izin Cookie-Editor ke instagram.com",
    description:
      'Klik icon Cookie-Editor di toolbar (1), lalu pilih "This site" (2) untuk memberi akses ke cookies instagram.com.',
    img: "/guide/6.png",
  },
  {
    title: "Temukan & copy nilai sessionid",
    description:
      "Di daftar cookies, klik sessionid (1). Nilai lengkapnya akan muncul di bawah — copy nilai tersebut (2) lalu paste di form Add Session di app.",
    img: "/guide/12.png",
    note: {
      type: "info",
      text: "Sessions hanya butuh nilai sessionid saja — bukan seluruh JSON. Nilainya berupa string panjang seperti 3361804...amQ",
    },
  },
];

const STEPS_SCRAPINGBOT: StepDef[] = [
  {
    title: "Buat email temporary di TempMail",
    description:
      "Buka temp-mail.org — email temporary sudah langsung tersedia. Klik Copy untuk menyalin alamat email ini, kita akan pakai untuk daftar akun ScrapingBot.",
    img: "/guide/13.png",
    note: {
      type: "info",
      text: "Pakai temp email agar kamu bisa daftar banyak akun ScrapingBot gratis dan merotasinya secara otomatis di app.",
      link: {
        label: "Buka TempMail",
        href: "https://temp-mail.org/en/",
      },
    },
  },
  {
    title: "Daftar akun ScrapingBot",
    description:
      "Buka scraping-bot.io, klik Sign up for free. Isi form registrasi: nama, email (paste dari TempMail), username unik, dan password. Klik Submit.",
    img: "/guide/14.png",
    note: {
      type: "info",
      text: "Setiap akun free tier dapat 500 kredit/bulan — daftarkan beberapa akun dengan email temporary berbeda untuk kuota lebih besar.",
      link: {
        label: "scraping-bot.io — Sign up",
        href: "https://www.scraping-bot.io/register/",
      },
    },
  },
  {
    title: "Salin Username & API Key",
    description:
      "Setelah login ke dashboard ScrapingBot, catat YOUR USERNAME dan YOUR API KEY yang tampil di halaman utama. Keduanya dibutuhkan untuk ditambahkan ke app.",
    img: "/guide/15.png",
    note: {
      type: "warning",
      text: "Jangan share API Key kamu. Jika bocor, klik Regen API KEY untuk generate ulang.",
    },
  },
  {
    title: "Tambahkan akun ke app",
    description:
      "Buka Settings → Instagram → tab ScrapingBot. Klik Tambah Akun, isi Username dan API Key dari dashboard tadi, lalu klik Tambah.",
    img: "/guide/16.png",
  },
];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function GuideImage({ src, alt }: { src: string; alt: string }) {
  const [err, setErr] = useState(false);

  useEffect(() => {
    setErr(false);
  }, [src]);

  return (
    <div className="aspect-video w-full overflow-hidden rounded-xl border border-gray-200 bg-gray-100 dark:border-gray-700 dark:bg-gray-700/50">
      {err ? (
        <div className="flex h-full flex-col items-center justify-center gap-2 text-gray-300 dark:text-gray-600">
          <ImageIcon className="h-10 w-10" />
          <span className="text-xs">Screenshot belum tersedia</span>
        </div>
      ) : (
        <img
          src={src}
          alt={alt}
          className="h-full w-full object-cover object-top"
          onError={() => setErr(true)}
        />
      )}
    </div>
  );
}

function StepDot({ active, passed }: { active: boolean; passed: boolean }) {
  return (
    <div
      className={`h-2 w-2 rounded-full transition-all duration-200 ${
        active
          ? "scale-125 bg-orange-400"
          : passed
            ? "bg-orange-200 dark:bg-orange-700"
            : "bg-gray-200 dark:bg-gray-600"
      }`}
    />
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function IGSetupGuideModal({
  isOpen,
  onClose,
  initialTab = "accounts",
  onOpenCookieImport,
}: Props) {
  const [tab, setTab] = useState<GuideTab>(initialTab);
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (isOpen) {
      setTab(initialTab);
      setStep(0);
    }
  }, [isOpen, initialTab]);

  if (!isOpen) return null;

  const steps =
    tab === "accounts"
      ? STEPS_ACCOUNTS
      : tab === "sessions"
        ? STEPS_SESSIONS
        : STEPS_SCRAPINGBOT;
  const current = steps[step];
  const isFirst = step === 0;
  const isLast = step === steps.length - 1;

  const handleTabChange = (newTab: GuideTab) => {
    setTab(newTab);
    setStep(0);
  };

  const handleNext = () => {
    if (isLast) {
      onClose();
    } else {
      setStep((s) => s + 1);
    }
  };

  const handleCtaClick = () => {
    onClose();
    onOpenCookieImport?.();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="flex w-full max-w-2xl mx-4 max-h-[90vh] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-gray-800">
        {/* Header */}
        <div className="flex flex-shrink-0 items-center justify-between bg-gradient-to-r from-purple-500 via-pink-500 to-orange-400 px-5 py-4">
          <div className="flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-white" />
            <span className="font-semibold text-white">
              Instagram Setup Guide
            </span>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-1 transition-colors hover:bg-white/20"
          >
            <X className="h-5 w-5 text-white" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          <div className="space-y-5 p-5">
            {/* Tab switcher */}
            <div className="flex w-fit gap-1 rounded-xl bg-gray-100 p-1 dark:bg-gray-700/60">
              <button
                onClick={() => handleTabChange("accounts")}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-all ${
                  tab === "accounts"
                    ? "bg-white text-gray-900 shadow-sm dark:bg-gray-600 dark:text-gray-100"
                    : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                }`}
              >
                <Instagram className="h-3.5 w-3.5" />
                IG Accounts
              </button>
              <button
                onClick={() => handleTabChange("sessions")}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-all ${
                  tab === "sessions"
                    ? "bg-white text-gray-900 shadow-sm dark:bg-gray-600 dark:text-gray-100"
                    : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                }`}
              >
                <Cookie className="h-3.5 w-3.5" />
                Sessions
              </button>
              <button
                onClick={() => handleTabChange("scrapingbot")}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-all ${
                  tab === "scrapingbot"
                    ? "bg-white text-gray-900 shadow-sm dark:bg-gray-600 dark:text-gray-100"
                    : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                }`}
              >
                <Bot className="h-3.5 w-3.5" />
                ScrapingBot
              </button>
            </div>

            {/* Step dots */}
            <div className="flex items-center gap-1.5">
              {steps.map((_, i) => (
                <StepDot key={i} active={i === step} passed={i < step} />
              ))}
            </div>

            {/* Step content */}
            <div className="space-y-3">
              {/* Step header */}
              <div className="flex items-center gap-3">
                <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-orange-500 text-xs font-bold text-white">
                  {step + 1}
                </span>
                <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                  {current.title}
                </h3>
              </div>

              {/* Description */}
              <p className="pl-10 text-sm leading-relaxed text-gray-600 dark:text-gray-300">
                {current.description}
              </p>

              {/* Image */}
              <GuideImage src={current.img} alt={current.title} />

              {/* Note */}
              {current.note && (
                <div
                  className={`flex items-start gap-2.5 rounded-xl border p-3 text-xs ${
                    current.note.type === "warning"
                      ? "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-300"
                      : "border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-700/50 dark:bg-blue-900/20 dark:text-blue-300"
                  }`}
                >
                  {current.note.type === "warning" ? (
                    <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                  ) : (
                    <Info className="mt-0.5 h-4 w-4 flex-shrink-0" />
                  )}
                  <div className="space-y-1.5">
                    <p>{current.note.text}</p>
                    {current.note.link && (
                      <a
                        href={current.note.link.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 font-medium underline underline-offset-2 hover:opacity-80"
                      >
                        {current.note.link.label}
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex flex-shrink-0 items-center justify-between border-t border-gray-100 px-5 py-4 dark:border-gray-700">
          <span className="text-xs text-gray-400 dark:text-gray-500">
            {step + 1} / {steps.length}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setStep((s) => s - 1)}
              disabled={isFirst}
              className="flex items-center gap-1.5 rounded-xl bg-gray-100 px-4 py-2.5 text-sm font-semibold text-gray-700 transition-colors hover:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
            >
              <ChevronLeft className="h-4 w-4" />
              Sebelumnya
            </button>

            {/* CTA: Import Cookies button on final step */}
            {isLast && current.isCta && onOpenCookieImport ? (
              <button
                onClick={handleCtaClick}
                className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-400 px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90"
              >
                <MousePointerClick className="h-4 w-4" />
                Import Cookies
              </button>
            ) : (
              <button
                onClick={handleNext}
                className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-pink-500 to-orange-400 px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90"
              >
                {isLast ? "Selesai" : "Selanjutnya"}
                {!isLast && <ChevronRight className="h-4 w-4" />}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
