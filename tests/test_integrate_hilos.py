import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import integrate_hilos


class IntegrateHilosTests(unittest.TestCase):
    def test_parses_legacy_markdown_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Acta_1_2026-01-01.md"
            path.write_text(
                "# Acta\n\n## Episodios\n\n### → Hilo: `Hilo`\n\n"
                "#### 2026-01-01 — Titulo\n\nTexto.\n\n"
                "> Fuente: Acta N° 1, 01 de enero del 2026.\n",
                encoding="utf-8",
            )
            episodes = integrate_hilos.parse_acta(path)
        self.assertEqual(episodes[0]["hilo"], "Hilo")
        self.assertEqual(episodes[0]["date"], "2026-01-01")

    def test_parses_v2_frontmatter_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Acta_2_2026-01-08.md"
            path.write_text(
                "---\nversion_formato: 2\nepisodios:\n"
                "  - episodio_id: acta-2-art-i-item-1\n"
                "    fecha: 2026-01-08\n"
                "    titulo: Titulo estructurado\n"
                "    hilo_destino: Hilo\n"
                "    tipo: evidencia\n"
                "    cuerpo: Texto.\n"
                "    cita: Acta N° 2, Articulo I, item 1.\n---\n",
                encoding="utf-8",
            )
            episodes = integrate_hilos.parse_acta(path)
        self.assertEqual(episodes[0]["episode_id"], "acta-2-art-i-item-1")
        self.assertEqual(episodes[0]["fuente"], "> Fuente: Acta N° 2, Articulo I, item 1.")

    def test_appending_preserves_existing_hilo_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Hilo.md"
            original = "## Contexto heredado\n\nTexto curado.\n"
            path.write_text(original, encoding="utf-8")
            episode = {
                "date": "2026-01-01",
                "title": "Titulo",
                "body": "Texto.",
                "fuente": "> Fuente: Acta N° 1.",
            }
            integrate_hilos.append_episodes(path, [episode])
            updated = path.read_text(encoding="utf-8")
        self.assertTrue(updated.startswith(original))
        self.assertIn("### 2026-01-01 — Titulo", updated)


if __name__ == "__main__":
    unittest.main()
