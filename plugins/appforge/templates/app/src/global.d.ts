import type { Locale } from "./i18n/config";

// Message keys of the generated `model` namespace are built at run time
// (model.entities.<key>.fields.<field>): messages are not typed statically.
declare module "next-intl" {
  interface AppConfig {
    Locale: Locale;
  }
}
