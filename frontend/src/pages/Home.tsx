import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Module } from "../api";
import { PageHeader } from "../components/ui";
import { useSession } from "../session";

export function Home() {
  const { user, company, canManageCompany } = useSession();
  const [catalog, setCatalog] = useState<Module[]>([]);
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    api.modules().then(setCatalog, () => {});
    api.health().then((h) => setVersion(h.version), () => {});
  }, []);

  if (!user) return null;
  const firstName = user.full_name.split(" ")[0];

  if (!company) {
    return (
      <>
        <PageHeader title={`Bonjour ${firstName}`} />
        <section className="card empty">
          <h2>Aucune entreprise ne vous est rattachée</h2>
          <p className="muted">
            Demandez à l'administrateur du boîtier de vous donner accès à une entreprise.
          </p>
        </section>
      </>
    );
  }

  const enabled = catalog.filter((m) => company.enabled_modules.includes(m.key));

  return (
    <>
      <PageHeader title={`Bonjour ${firstName}`} lead={company.name} />

      <section className="card empty">
        <h2>Le boîtier est prêt à recevoir vos données</h2>
        <p className="muted">
          Aucun document n'a encore été importé : il n'y a donc aucun indicateur à afficher.
          L'import de factures et le tableau de bord financier arrivent avec la prochaine version.
        </p>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>Modules activés</h2>
          {canManageCompany && (
            <Link className="btn" to="/parametres/entreprise">
              Modifier
            </Link>
          )}
        </div>
        {enabled.length === 0 ? (
          <p className="muted">Aucun module n'est activé pour cette entreprise.</p>
        ) : (
          <ul className="module-list">
            {enabled.map((module) => (
              <li key={module.key}>
                <span>
                  <strong>{module.name}</strong>
                  <span className="muted module-text">{module.description}</span>
                </span>
                {!module.available && <span className="tag">À venir</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      {version && <p className="muted small">Business AI Box — version {version}</p>}
    </>
  );
}
