"""Testes de regressão para os diagnósticos meteorológicos do Vale1Km."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import leitura
import termo
import gerar_namelists


class TestTemperaturaWRF(unittest.TestCase):
    def test_reconstrucao_theta_m_com_umidade(self):
        theta_pert = np.array([10.0])
        razao_mistura = np.array([0.01])
        pressao = np.array([90000.0])
        esperado = 310.0 / (1.0 + 1.61 * 0.01) * (90000.0 / 100000.0) ** leitura.KAPPA_WRF
        obtido = leitura.temperatura_wrf(theta_pert, razao_mistura, pressao)
        np.testing.assert_allclose(obtido, [esperado], rtol=1e-12)

    def test_ar_seco_reduz_para_formula_theta_convencional(self):
        theta_pert = np.array([15.0])
        pressao = np.array([95000.0])
        esperado = 315.0 * (0.95 ** leitura.KAPPA_WRF)
        obtido = leitura.temperatura_wrf(theta_pert, np.array([0.0]), pressao)
        np.testing.assert_allclose(obtido, [esperado], rtol=1e-12)


class TestVorticidadeGrade(unittest.TestCase):
    def test_rotacao_solida_reproduz_vorticidade_analitica(self):
        ny, nx = 9, 11
        dx = dy = 1000.0
        omega = 0.002
        x = np.arange(nx) * dx
        y = np.arange(ny) * dy
        xx, yy = np.meshgrid(x, y)
        u = -omega * yy
        v = omega * xx
        mfu = np.ones((ny, nx + 1))
        mfv = np.ones((ny + 1, nx))
        mfm = np.ones((ny, nx))
        obtida = termo.vorticidade_relativa_grade(u, v, mfu, mfv, mfm, dx, dy)
        np.testing.assert_allclose(obtida, 2.0 * omega, rtol=1e-12, atol=1e-12)

    def test_rejeita_fatores_de_escala_com_formato_invalido(self):
        campo = np.zeros((5, 6))
        with self.assertRaises(ValueError):
            termo.vorticidade_relativa_grade(
                campo, campo, np.ones((5, 6)), np.ones((6, 6)), np.ones((5, 6)), 1000.0, 1000.0
            )


class TestVorticidadeSuperficies(unittest.TestCase):
    def test_vorticidade_altura_constante_remove_termo_de_cisalhamento_eta(self):
        ny, nx = 13, 15
        dx = dy = 1000.0
        omega = 0.001
        x = np.arange(nx) * dx
        y = np.arange(ny) * dy
        xx, yy = np.meshgrid(x, y)
        zlev = np.array([0.0, 2000.0, 4000.0, 6000.0, 8000.0])[:, None, None]
        z = zlev + 0.01 * yy[None, :, :]
        u = -omega * yy[None, :, :] + 0.003 * z
        v = omega * xx[None, :, :] - 0.002 * z
        alturas = np.array([2500.0, 3500.0, 4500.0])
        mfu = np.ones((ny, nx + 1))
        mfv = np.ones((ny + 1, nx))
        mfm = np.ones((ny, nx))
        obtida = termo.vorticidade_em_altura_agl(z, u, v, alturas, mfu, mfv, mfm, dx, dy)
        np.testing.assert_allclose(obtida[:, 2:-2, 2:-2], 2.0 * omega, rtol=1e-10, atol=1e-10)

    def test_vorticidade_850hpa_mascara_pontos_abaixo_do_solo(self):
        ny, nx = 4, 5
        dx = dy = 1000.0
        omega = 0.001
        x = np.arange(nx) * dx
        y = np.arange(ny) * dy
        xx, yy = np.meshgrid(x, y)
        p = np.broadcast_to(np.array([100000.0, 90000.0, 80000.0, 70000.0])[:, None, None], (4, ny, nx))
        u = np.broadcast_to((-omega * yy)[None, :, :], p.shape)
        v = np.broadcast_to((omega * xx)[None, :, :], p.shape)
        psfc = np.full((ny, nx), 95000.0)
        psfc[0, 0] = 84000.0
        mfu = np.ones((ny, nx + 1))
        mfv = np.ones((ny + 1, nx))
        mfm = np.ones((ny, nx))
        obtida = termo.vorticidade_em_pressao(p, u, v, 85000.0, mfu, mfv, mfm, dx, dy, psfc)
        self.assertTrue(np.isnan(obtida[0, 0]))
        self.assertTrue(np.isfinite(obtida[1, 1]))
        np.testing.assert_allclose(obtida[1:, 1:], 2.0 * omega, rtol=1e-10, atol=1e-10)


class TestNamelistNWP(unittest.TestCase):
    def test_habilita_diagnosticos_nativos_na_secao_time_control(self):
        manifesto = {"horarios_utc": ["2026-11-16T00", "2026-11-16T03"]}
        texto = gerar_namelists.entrada(manifesto, "2026-11-16T03", 19)
        time_control = texto.split("&time_control", 1)[1].split("&domains", 1)[0]
        self.assertRegex(time_control, r"nwp_diagnostics\s*=\s*1")
        self.assertIn("history_interval = 60, 60, 60", time_control)


class TestJanelaUH(unittest.TestCase):
    def test_aceita_janela_completa_em_cadencia_de_dez_minutos(self):
        fim = leitura.datetime(2026, 11, 18, 18, 0)
        tempos = [fim - leitura.timedelta(minutes=60 - 10 * k) for k in range(7)]
        self.assertEqual(leitura.indices_janela_uh(tempos, fim), list(range(7)))

    def test_rejeita_primeira_hora_com_apenas_uma_amostra(self):
        fim = leitura.datetime(2026, 11, 18, 17, 0)
        self.assertEqual(leitura.indices_janela_uh([fim], fim), [])

    def test_rejeita_janela_com_lacuna_maior_que_dez_minutos(self):
        fim = leitura.datetime(2026, 11, 18, 18, 0)
        tempos = [fim - leitura.timedelta(minutes=60 - 10 * k) for k in range(7)]
        tempos.pop(3)
        self.assertEqual(leitura.indices_janela_uh(tempos, fim), [])


class TestSinalSRH(unittest.TestCase):
    def test_srh_segue_convecao_de_metpy(self):
        # Soma padrao: (u_top-cx)*(v_bottom-cy) - (u_bottom-cx)*(v_top-cy).
        h = np.array([0.0, 1000.0])
        u = np.array([10.0, 0.0])
        v = np.array([0.0, -10.0])
        srh = termo.srh(u, v, h, (0.0, 0.0), 0.0, 1000.0)
        self.assertAlmostEqual(float(srh), 100.0)

    def test_srh_ciclonica_no_hs_com_bunkers_left_mover(self):
        # Cisalhamento de oeste em altura: a left mover no HS deve resultar negativa.
        h = np.array([0.0, 6000.0])
        u = np.array([0.0, 10.0])
        v = np.array([0.0, 0.0])
        _mean, _rm, lm, _shear = termo.bunkers(u, v, h)
        valor = termo.srh(u, v, h, lm, 0.0, 6000.0)
        self.assertAlmostEqual(float(valor), -75.0)

    def test_srh_invariante_a_translacao_comum(self):
        u = np.array([12.0, 8.0, 3.0])
        v = np.array([1.0, -4.0, -9.0])
        h = np.array([0.0, 500.0, 1000.0])
        base = termo.srh(u, v, h, (2.0, -1.0), 0.0, 1000.0)
        transladado = termo.srh(u + 7.0, v - 3.0, h, (9.0, -4.0), 0.0, 1000.0)
        self.assertAlmostEqual(float(base), float(transladado))

    def test_srh_independe_de_translacao_uniforme_do_vento_e_da_tempestade(self):
        u = np.array([12.0, 8.0, 3.0])
        v = np.array([1.0, -4.0, -9.0])
        h = np.array([0.0, 500.0, 1000.0])
        base = termo.srh(u, v, h, (2.0, -1.0), 0.0, 1000.0)
        transladado = termo.srh(u + 7.0, v - 3.0, h, (9.0, -4.0), 0.0, 1000.0)
        self.assertAlmostEqual(float(base), float(transladado))


if __name__ == "__main__":
    unittest.main()
