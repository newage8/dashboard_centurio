import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# 1. Configuração Visual da Tubasa Labs
sns.set_theme(style="darkgrid", palette="deep")
plt.rcParams['figure.figsize'] = (12, 6)

# 2. Leitura Estrutural do Cofre
caminho = r"C:\Tubasa_Labs\data_profit\NewAgeTubasaLabSafe01.csv"
try:
    df = pd.read_csv(caminho, encoding='iso-8859-1', sep=';', skiprows=5)
except FileNotFoundError:
    print("ERRO: O arquivo não foi encontrado. Verifique se ele está na exata pasta 'data_profit'.")
    exit()

# 3. Conversão Financeira Institucional
df['Lucro_Prejuizo'] = df['Res. Operação'].astype(str).str.replace('.', '').str.replace(',', '.').astype(float)
df['Patrimonio_Acumulado'] = df['Lucro_Prejuizo'].cumsum()

# 4. Cálculo das Métricas Centurion
total_trades = len(df)
wins = len(df[df['Lucro_Prejuizo'] > 0])
win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
lucro_bruto = df[df['Lucro_Prejuizo'] > 0]['Lucro_Prejuizo'].sum()
prejuizo_bruto = abs(df[df['Lucro_Prejuizo'] < 0]['Lucro_Prejuizo'].sum())
profit_factor = lucro_bruto / prejuizo_bruto if prejuizo_bruto > 0 else float('inf')
resultado_liquido = df['Lucro_Prejuizo'].sum()

print("=== DASHBOARD CENTURION - INTELIGÊNCIA TÁTICA ===")
print(f"Operações Totais: {total_trades}")
print(f"Taxa de Acerto: {win_rate:.2f}%")
print(f"Fator de Lucro: {profit_factor:.2f}")
print(f"Resultado Operacional Bruto: R$ {resultado_liquido:.2f}\n")

# 5. Projeção Gráfica (Curva do Estado de Presença)
plt.plot(df.index, df['Patrimonio_Acumulado'], color='lime', linewidth=2, label='Evolução Institucional (Safe)')
plt.fill_between(df.index, df['Patrimonio_Acumulado'], color='lime', alpha=0.1)
plt.title('Centurion GPS - Patrimônio Acumulado (Trade Arena)', fontsize=14, color='white', backgroundcolor='black')
plt.xlabel('Quantidade de Operações', fontsize=12)
plt.ylabel('Lucro Acumulado Bruto (R$)', fontsize=12)
plt.axhline(0, color='red', linestyle='--', linewidth=1)
plt.legend()
plt.tight_layout()
plt.show()