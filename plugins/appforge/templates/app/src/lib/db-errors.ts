// Errors raised by the generated SQL (raise exception '<Italian text>') mapped to
// keys of the `errors` namespace. Hand-written SQL: add its messages here
// (tests/i18n.test.ts fails when a message is not mapped).
const MESSAGES: [RegExp, string][] = [
  [/^Operazione riservata agli amministratori/, "adminOnly"],
  [/^Operazione non consentita/, "forbidden"],
  [/^Record non trovato/, "notFound"],
  [/^Utente non trovato/, "notFound"],
  [/^Evento non trovato/, "notFound"],
  [/^Transizione non disponibile/, "transitionUnavailable"],
  [/^Transizione sconosciuta/, "transitionUnavailable"],
  [/^Transizione automatica/, "transitionAutomatic"],
  [/^Requisiti non soddisfatti/, "unmetRequirements"],
  [/^Commento obbligatorio/, "commentRequired"],
  [/^Lo stato cambia solo tramite le transizioni/, "stateLocked"],
  [/^Campo di sola lettura/, "readonlyField"],
  [/^Il ruolo .* richiede un ambito/, "roleNeedsScope"],
  [/^Il ruolo .* non ha ambito/, "roleWithoutScope"],
  [/^Entità sconosciuta/, "unknownEntity"],
  [/^Entità senza workflow/, "unknownEntity"],
  [/^Troppe reazioni annidate/, "reactionLoop"],
  [/^Dominio email non autorizzato/, "domain"],
];

export function dbMessageKey(message: string): string | null {
  for (const [re, key] of MESSAGES) if (re.test(message)) return key;
  return null;
}
