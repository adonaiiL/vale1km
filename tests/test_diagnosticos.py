"""Testes de regressão para os diagnósticos meteorológicos do Vale1Km."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import leitura
import termo


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


class TestSinalSRH(unittest.TestCase):
    def test_giro_horario_tem_srh_negativa(self):
        # Vetor do vento gira de leste para sul com a altura: giro horário.
        u = np.array([10.0, 0.0])
        v = np.array([0.0, -10.0])
        srh = termo.srh(u, v, np.array([0.0, 1000.0]), (0.0, 0.0), 0.0, 1000.0)
        self.assertAlmostEqual(float(srh), -100.0)

    def test_giro_anti_horario_tem_srh_positiva(self):
        u = np.array([10.0, 0.0])
        v = np.array([0.0, 10.0])
        srh = termo.srh(u, v, np.array([0.0, 1000.0]), (0.0, 0.0), 0.0, 1000.0)
        self.assertAlmostEqual(float(srh), 100.0)

    def test_srh_independe_de_translacao_uniforme_do_vento_e_da_tempestade(self):
        u = np.array([12.0, 8.0, 3.0])
        v = np.array([1.0, -4.0, -9.0])
        h = np.array([0.0, 500.0, 1000.0])
        base = termo.srh(u, v, h, (2.0, -1.0), 0.0, 1000.0)
        transladado = termo.srh(u + 7.0, v - 3.0, h, (9.0, -4.0), 0.0, 1000.0)
        self.assertAlmostEqual(float(base), float(transladado))


if __name__ == "__main__":
    unittest.main()
