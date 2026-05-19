import tkinter as tk
from tkinter import messagebox, ttk
from CoolProp.CoolProp import PropsSI

class AirContentTest:
    def __init__(self, diameter, thickness, length, A, K):
        self.diameter = diameter
        self.thickness = thickness
        self.length = length
        self.A = A
        self.K = K
    
    def calculate_vt(self):
        radius = self.diameter / 2
        return (3.1416 * (radius ** 2) * self.length) / 1000000  
    
    def calculate_ri(self):
        return self.diameter / 2 - self.thickness
    
    def calculate_vp(self):
        ri = self.calculate_ri()
        Vt = self.calculate_vt()
        return ((0.884 * ri / self.thickness) + self.A) * Vt * self.K / 1000000
    
    def check_test_success(self, Vpa):
        Vp = self.calculate_vp()
        ratio = Vpa / Vp
        return ratio <= 1.06, ratio

class PressureTest:
    def __init__(self, diameter, thickness, A, B, delta_T, Pa):
        self.diameter = diameter
        self.thickness = thickness
        self.A = A
        self.B = B
        self.delta_T = delta_T
        self.Pa = Pa
    
    def calculate_ri(self):
        return self.diameter / 2 - self.thickness
    
    def calculate_delta_P(self):
        ri = self.calculate_ri()
        return (self.B * self.delta_T) / ((0.884 * ri / self.thickness) + self.A)

def calculate_A(entry_temperature, entry_pressure, entry_A):
    try:
        T = float(entry_temperature.get()) + 273.15  
        P = float(entry_pressure.get()) * 1e5  
        A = PropsSI("ISOTHERMAL_COMPRESSIBILITY", "T", T, "P", P, "Water")
        entry_A.delete(0, tk.END)
        entry_A.insert(0, f"{A:.6e}")
        return A
    except ValueError:
        messagebox.showerror("Hata", "Geçerli sıcaklık ve basınç değerleri girin!")
        return None

def run_air_content_test():
    try:
        diameter = float(entry_diameter.get())
        thickness = float(entry_thickness.get())
        length = float(entry_length.get())
        A = float(entry_A1.get())
        K = float(var_K.get())
        Vpa = float(entry_Vpa.get())
        
        test = AirContentTest(diameter, thickness, length, A, K)
        success, ratio = test.check_test_success(Vpa)
        
        result_msg = (f"Hava içerik testi başarılı mı?: {'Evet' if success else 'Hayır'}\n"
                      f"Vpa/Vp oranı: {ratio:.2f}")
        messagebox.showinfo("Sonuçlar", result_msg)
    except ValueError:
        messagebox.showerror("Hata", "Lütfen tüm alanlara geçerli sayısal değerler girin!")

def run_pressure_test():
    try:
        diameter = float(entry_diameter.get())
        thickness = float(entry_thickness.get())
        A = float(entry_A2.get())
        delta_T = float(entry_delta_T.get())
        Pa = float(entry_Pa.get())
        B = A - 1.2e-5  
        
        test = PressureTest(diameter, thickness, A, B, delta_T, Pa)
        delta_P = test.calculate_delta_P()
        
        result_msg = f"Basınç Testi Sonucu: ΔP = {delta_P:.6f} bar"
        messagebox.showinfo("Sonuçlar", result_msg)
    except ValueError:
        messagebox.showerror("Hata", "Lütfen tüm alanlara geçerli sayısal değerler girin!")

root = tk.Tk()
root.title("Boru Hattı Testleri")

notebook = ttk.Notebook(root)
frame_input = ttk.Frame(notebook)
frame_result = ttk.Frame(notebook)
notebook.add(frame_input, text="Giriş")
notebook.add(frame_result, text="Sonuçlar")
notebook.pack(expand=True, fill="both")

tk.Label(frame_input, text="Boru çapı (mm):").grid(row=0, column=0)
entry_diameter = tk.Entry(frame_input)
entry_diameter.grid(row=0, column=1)

tk.Label(frame_input, text="Boru et kalınlığı (mm):").grid(row=1, column=0)
entry_thickness = tk.Entry(frame_input)
entry_thickness.grid(row=1, column=1)

tk.Label(frame_input, text="Boru hattı uzunluğu (m):").grid(row=2, column=0)
entry_length = tk.Entry(frame_input)
entry_length.grid(row=2, column=1)

tk.Label(frame_input, text="Hava İçerik Testi - Sıcaklık (°C):").grid(row=3, column=0)
entry_temperature1 = tk.Entry(frame_input)
entry_temperature1.grid(row=3, column=1)

tk.Label(frame_input, text="Hava İçerik Testi - Basınç (bar):").grid(row=4, column=0)
entry_pressure1 = tk.Entry(frame_input)
entry_pressure1.grid(row=4, column=1)

tk.Label(frame_input, text="Basınç Testi - Sıcaklık (°C):").grid(row=5, column=0)
entry_temperature2 = tk.Entry(frame_input)
entry_temperature2.grid(row=5, column=1)

tk.Label(frame_input, text="Basınç Testi - Basınç (bar):").grid(row=6, column=0)
entry_pressure2 = tk.Entry(frame_input)
entry_pressure2.grid(row=6, column=1)

tk.Label(frame_input, text="Fiili basınç değişikliği Pa (bar):").grid(row=7, column=0)
entry_Pa = tk.Entry(frame_input)
entry_Pa.grid(row=7, column=1)

entry_A1 = tk.Entry(frame_input)
entry_A2 = tk.Entry(frame_input)
tk.Button(frame_input, text="Hava İçerik A Hesapla", command=lambda: calculate_A(entry_temperature1, entry_pressure1, entry_A1)).grid(row=3, column=2)
tk.Button(frame_input, text="Basınç Testi A Hesapla", command=lambda: calculate_A(entry_temperature2, entry_pressure2, entry_A2)).grid(row=5, column=2)

root.mainloop()
