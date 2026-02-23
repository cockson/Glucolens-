import i18n from "i18next";
import { initReactI18next } from "react-i18next";

const resources = {
  en: { translation: {
    appName: "GlucoLens",
    login: "Login",
    registerBusiness: "Register Business",
    registerPublic: "Quick Check (Public)",
    logout: "Logout",
    billing: "Billing",
    referrals: "Referrals",
    facilities: "Facilities",
  }},
  fr: { translation: { appName: "GlucoLens" } },
  sw: { translation: { appName: "GlucoLens" } },
};

i18n.use(initReactI18next).init({
  resources,
  lng: import.meta.env.VITE_DEFAULT_LANG || "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export default i18n;