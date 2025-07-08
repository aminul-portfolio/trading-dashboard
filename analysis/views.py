
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.core.paginator import Paginator
from .models import SimulationHistory

import pandas as pd
import numpy as np
import base64
from io import BytesIO
import matplotlib.pyplot as plt
import json


from .models import Trade, Screenshot
from .forms import (
    ScreenshotForm,
    LotSizeForm,
    RiskPerTradeForm,
    StrategyRiskForm,
    SLTPForm,
    MonteCarloForm
)


def home(request):
    features = [
        {
            "title": "Data Upload",
            "description": "Upload trading CSV or Excel files with automatic column detection and validation.",
            "icon": "bi bi-upload",
            "color": "primary",
            "url": "/upload/",
            "button_text": "Go to Upload"
        },
        {
            "title": "Dashboard",
            "description": "Summarize trading performance, profit metrics, and strategy effectiveness.",
            "icon": "bi bi-speedometer2",
            "color": "success",
            "url": "/dashboard/",
            "button_text": "View Dashboard"
        },
        {
            "title": "Calculators",
            "description": "Lot size, risk per trade, strategy risk, and SL/TP calculators.",
            "icon": "bi bi-calculator",
            "color": "warning",
            "url": "/calculators/lot-size/",
            "button_text": "Open Calculators"
        },
        {
            "title": "Monte Carlo Simulation",
            "description": "Stress-test your strategy with random outcome simulations.",
            "icon": "bi bi-shuffle",
            "color": "info",
            "url": "/monte-carlo/",
            "button_text": "Run Simulation"
        },
        {
            "title": "Admin Panel",
            "description": "Manage uploaded trades, users, and system settings through Django Admin.",
            "icon": "bi bi-gear",
            "color": "secondary",
            "url": "/admin/",
            "button_text": "Open Admin"
        },
        {
            "title": "Demo Video",
            "description": "Watch a walkthrough demonstrating the project features.",
            "icon": "bi bi-play-circle",
            "color": "danger",
            "url": "https://www.youtube.com/",
            "button_text": "Watch Demo"
        },
    ]

    screenshots = Screenshot.objects.order_by("-uploaded_at")
    form = ScreenshotForm()

    return render(request, "analysis/home.html", {
        "features": features,
        "screenshots": screenshots,
        "form": form
    })


def upload_screenshot(request):
    if request.method == "POST":
        form = ScreenshotForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
    return redirect("home")


def delete_screenshot(request, pk):
    screenshot = get_object_or_404(Screenshot, pk=pk)
    if request.method == "POST":
        screenshot.image.delete()
        screenshot.delete()
    return redirect("home")


def upload_file(request):
    if request.method == 'POST' and request.FILES.get('file'):
        file = request.FILES['file']
        filename = file.name.lower()

        # Read file
        if filename.endswith('.csv'):
            df = pd.read_csv(file)
        elif filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file)
        else:
            return render(request, 'analysis/upload.html', {
                'error': 'Unsupported file type. Please upload CSV or Excel.'
            })

        # Normalize columns
        df.columns = df.columns.str.strip().str.lower()

        # Define defaults
        required = {
            'date': pd.NaT,
            'symbol': 'UNKNOWN',
            'volume': 0,
            'entryprice': 0,
            'exitprice': 0,
            'profit': 0,
            'accounttype': 'Personal'
        }

        # Fill missing columns
        for col, default in required.items():
            if col not in df.columns:
                df[col] = default

        # Create Trade records
        for _, row in df.iterrows():
            date = None
            if pd.notnull(row['date']):
                try:
                    date = pd.to_datetime(row['date']).date()
                except Exception:
                    date = None

            Trade.objects.create(
                user=request.user,  # <-- ADD THIS
                date=date,
                symbol=row['symbol'],
                volume=row['volume'],
                entry_price=row['entryprice'],
                exit_price=row['exitprice'],
                profit=row['profit'],
                account_type=row['accounttype'].capitalize() if pd.notnull(row['accounttype']) else 'Personal'
            )

        return redirect('dashboard')
    return render(request, 'analysis/upload.html')


def dashboard(request):
    trades = Trade.objects.all()
    if not trades:
        return render(request, 'analysis/dashboard.html', {'message': 'No trades uploaded yet.'})

    df = pd.DataFrame(list(trades.values()))

    context = {
        'total_profit': df['profit'].sum(),
        'win_rate': (df['profit'] > 0).mean() * 100,
        'max_drawdown': df['profit'].cumsum().min(),
        'avg_risk': df[df['profit'] < 0]['profit'].mean(),
        'volatility': df['profit'].std(),
        'percentile_95': np.percentile(df['profit'], 5)
    }
    return render(request, 'analysis/dashboard.html', context)


def lot_size_calculator(request):
    result = None
    if request.method == 'POST':
        form = LotSizeForm(request.POST)
        if form.is_valid():
            lot = form.cleaned_data['lot_size']
            pip_distance = form.cleaned_data['pip_distance']
            pip_value = form.cleaned_data['pip_value']
            result = pip_distance * lot * pip_value
    else:
        form = LotSizeForm()
    return render(request, 'analysis/lot_size.html', {'form': form, 'result': result})


def risk_per_trade_calculator(request):
    result = None
    if request.method == 'POST':
        form = RiskPerTradeForm(request.POST)
        if form.is_valid():
            acc_balance = form.cleaned_data['account_balance']
            lot = form.cleaned_data['lot_size']
            pip_val = form.cleaned_data['pip_value']
            sl_pips = form.cleaned_data['stop_loss_pips']
            risk_amount = sl_pips * lot * pip_val
            risk_percent = (risk_amount / acc_balance) * 100
            result = {'risk_amount': risk_amount, 'risk_percent': risk_percent}
    else:
        form = RiskPerTradeForm()
    return render(request, 'analysis/risk_per_trade.html', {'form': form, 'result': result})


def strategy_risk_calculator(request):
    result = None
    if request.method == 'POST':
        form = StrategyRiskForm(request.POST)
        if form.is_valid():
            base = form.cleaned_data['base_lot']
            win = form.cleaned_data['win_rate']
            rr = form.cleaned_data['rr']
            vol = form.cleaned_data['volatility']
            adjusted = base * (win / 50) * (rr / 2) * (200 / vol)
            result = adjusted
    else:
        form = StrategyRiskForm()
    return render(request, 'analysis/strategy_risk.html', {'form': form, 'result': result})


def sltp_calculator(request):
    result = None
    if request.method == 'POST':
        form = SLTPForm(request.POST)
        if form.is_valid():
            entry = form.cleaned_data['entry']
            sl = form.cleaned_data['stop_loss']
            tp = form.cleaned_data['take_profit']
            lot = form.cleaned_data['lot_size']
            pip_value = form.cleaned_data['pip_value']
            risk = abs(entry - sl) * lot * pip_value
            reward = abs(tp - entry) * lot * pip_value
            rr = reward / risk if risk != 0 else None
            result = {'risk': risk, 'reward': reward, 'rr': rr}
    else:
        form = SLTPForm()
    return render(request, 'analysis/sltp.html', {'form': form, 'result': result})



def monte_carlo_simulation(request):
    results = None
    profits = None
    instruction = None
    trade_count = None
    summary = None
    result_list = []
    form_data = {}
    date_start = None
    date_end = None

    if request.method == "POST":
        if "reset" in request.POST:
            request.session.pop("uploaded_df", None)
            return render(request, "analysis/monte_carlo.html", {
                "instruction": "Form reset successfully.",
                "form_data": {},
            })

        if request.FILES.get("file"):
            file = request.FILES["file"]
            filename = file.name.lower()

            if filename.endswith(".csv"):
                df = pd.read_csv(file)
            elif filename.endswith(".xlsx") or filename.endswith(".xls"):
                df = pd.read_excel(file)
            else:
                instruction = "Unsupported file type. Please upload CSV or Excel."
                return render(request, "analysis/monte_carlo.html", {"instruction": instruction})

            df.columns = df.columns.str.strip().str.lower()

            if "profit" not in df.columns:
                instruction = "Your file must have a 'profit' column."
                return render(request, "analysis/monte_carlo.html", {"instruction": instruction})

            if "close" in df.columns:
                try:
                    df["date"] = pd.to_datetime(df["close"])
                except Exception:
                    df["date"] = pd.NaT
            else:
                df["date"] = pd.NaT

            request.session["uploaded_df"] = df.to_json(date_format="iso")
            profits = df["profit"].dropna().values
            trade_count = len(profits)

            # Get date range
            if df["date"].notna().any():
                dates_non_null = df["date"].dropna()
                date_start = dates_non_null.min().strftime("%Y-%m-%d %H:%M")
                date_end = dates_non_null.max().strftime("%Y-%m-%d %H:%M")

            return render(request, "analysis/monte_carlo.html", {
                "trade_count": trade_count,
                "date_start": date_start,
                "date_end": date_end,
                "form_data": {},
            })

        if "uploaded_df" in request.session:
            df = pd.read_json(request.session["uploaded_df"])
            profits = df["profit"].dropna().values
            trade_count = len(profits)
        else:
            instruction = "Please upload a data file first."

        if profits is not None and "num_simulations" in request.POST:
            try:
                n_sim = int(request.POST.get("num_simulations", ""))
                n_trades = int(request.POST.get("num_trades", ""))
            except ValueError:
                instruction = "Please enter valid numbers for simulations and trades."
                return render(request, "analysis/monte_carlo.html", {
                    "instruction": instruction,
                    "trade_count": trade_count,
                })

            start = int(request.POST.get("range_start") or 0)
            end = int(request.POST.get("range_end") or len(profits))
            session = request.POST.get("session", "All")
            uk_start = request.POST.get("uk_start")
            uk_end = request.POST.get("uk_end")
            start_date = request.POST.get("start_date")
            end_date = request.POST.get("end_date")

            form_data = {
                "num_simulations": n_sim,
                "num_trades": n_trades,
                "range_start": start,
                "range_end": end,
                "session": session,
                "uk_start": uk_start,
                "uk_end": uk_end,
                "start_date": start_date,
                "end_date": end_date,
            }

            df_range = df.iloc[start:end]

            if session != "All" and df_range["date"].notna().any():
                if session == "UK":
                    df_range = df_range[df_range["date"].dt.hour.between(8, 17)]
                    if uk_start and uk_end:
                        try:
                            uk_start = int(uk_start)
                            uk_end = int(uk_end)
                            df_range = df_range[df_range["date"].dt.hour.between(uk_start, uk_end)]
                        except Exception:
                            pass
                elif session == "US":
                    df_range = df_range[df_range["date"].dt.hour.between(13, 22)]
                elif session == "Asia":
                    df_range = df_range[df_range["date"].dt.hour.between(0, 7)]

            if start_date and end_date:
                try:
                    start_dt = pd.to_datetime(start_date)
                    end_dt = pd.to_datetime(end_date)
                    df_range = df_range[df_range["date"].between(start_dt, end_dt)]
                except Exception:
                    pass

            profits_filtered = df_range["profit"].dropna().values

            summary = {
                "range_start": start,
                "range_end": end,
                "session": session,
                "trade_count": len(profits_filtered),
                "date_start": None,
                "date_end": None,
            }
            if df_range["date"].notna().any():
                dates_non_null = df_range["date"].dropna()
                summary["date_start"] = dates_non_null.min().strftime("%Y-%m-%d %H:%M")
                summary["date_end"] = dates_non_null.max().strftime("%Y-%m-%d %H:%M")

            if len(profits_filtered) == 0:
                instruction = "No trades matched your filters."
            else:
                ending_balances = []
                for _ in range(n_sim):
                    sim = np.random.choice(profits_filtered, size=n_trades, replace=True)
                    ending_balances.append(sim.sum())

                results = {
                    "min": np.min(ending_balances),
                    "max": np.max(ending_balances),
                    "median": np.median(ending_balances),
                    "prob_positive": (np.array(ending_balances) > 0).mean() * 100,
                    "trades_used": profits_filtered.tolist()
                }

                result_list = [
                    {"key": "min", "label": "Min Ending Balance", "icon": "bi-currency-dollar", "color": "danger", "value": results["min"], "is_percent": False},
                    {"key": "max", "label": "Max Ending Balance", "icon": "bi-currency-dollar", "color": "success", "value": results["max"], "is_percent": False},
                    {"key": "median", "label": "Median Ending Balance", "icon": "bi-currency-dollar", "color": "info", "value": results["median"], "is_percent": False},
                    {"key": "prob_positive", "label": "Probability of Profit", "icon": "bi-emoji-smile", "color": "primary", "value": results["prob_positive"], "is_percent": True},
                ]

    return render(request, "analysis/monte_carlo.html", {
        "instruction": instruction,
        "results": results,
        "result_list": result_list,
        "trade_count": trade_count,
        "summary": summary,
        "form_data": form_data,
        "date_start": date_start,
        "date_end": date_end,
    })



def simulation_run_view(request):
    results = None
    trade_count = None
    instruction = None
    form_data = {}
    result_list = []
    equity_curve_base64 = None
    date_start = None
    date_end = None

    if request.method == "POST":
        # Handle reset
        if "reset" in request.POST:
            request.session.pop("uploaded_df", None)
            return render(request, "analysis/simulation_run.html", {
                "instruction": "Form reset successfully.",
                "form_data": {},
            })

        # Handle file upload
        if request.FILES.get("file"):
            file = request.FILES["file"]
            df = pd.read_excel(file)
            df.columns = df.columns.str.strip().str.lower()

            if "profit" not in df.columns:
                instruction = "Your file must have a 'profit' column."
                return render(request, "analysis/simulation_run.html", {"instruction": instruction})

            if "open" in df.columns:
                df["date"] = pd.to_datetime(df["open"])
            else:
                df["date"] = pd.NaT

            request.session["uploaded_df"] = df.to_json(date_format="iso")

            trade_count = len(df)
            if df["date"].notna().any():
                dates = df["date"].dropna()
                date_start = dates.min().strftime("%Y-%m-%d %H:%M")
                date_end = dates.max().strftime("%Y-%m-%d %H:%M")

            return render(request, "analysis/simulation_run.html", {
                "trade_count": trade_count,
                "date_start": date_start,
                "date_end": date_end,
                "form_data": {},
            })

        # Load data from session
        if "uploaded_df" not in request.session:
            instruction = "Please upload a data file first."
            return render(request, "analysis/simulation_run.html", {"instruction": instruction})

        df = pd.read_json(request.session["uploaded_df"])
        trade_count = len(df)

        # Parse simulation parameters
        try:
            n_sim = int(request.POST.get("num_simulations"))
            n_trades = int(request.POST.get("num_trades"))
        except Exception:
            instruction = "Please enter valid numbers for simulations and trades."
            return render(request, "analysis/simulation_run.html", {
                "instruction": instruction,
                "trade_count": trade_count,
            })

        start = int(request.POST.get("range_start") or 0)
        end = int(request.POST.get("range_end") or len(df))
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date")

        form_data = {
            "num_simulations": n_sim,
            "num_trades": n_trades,
            "range_start": start,
            "range_end": end,
            "start_date": start_date,
            "end_date": end_date,
        }

        df_range = df.iloc[start:end]

        if start_date and end_date:
            try:
                sd = pd.to_datetime(start_date)
                ed = pd.to_datetime(end_date)
                df_range = df_range[df_range["date"].between(sd, ed)]
            except Exception:
                pass

        profits = df_range["profit"].dropna().values
        if len(profits) == 0:
            instruction = "No trades matched your filters."
            return render(request, "analysis/simulation_run.html", {
                "instruction": instruction,
                "trade_count": trade_count,
                "form_data": form_data,
            })

        # Simulate
        ending_balances = []
        equity_curves = []
        for _ in range(n_sim):
            sim = np.random.choice(profits, size=n_trades, replace=True)
            ending_balances.append(sim.sum())
            equity_curves.append(np.cumsum(sim))

        # Risk metrics
        results = {
            "min": np.min(ending_balances),
            "max": np.max(ending_balances),
            "median": np.median(ending_balances),
            "prob_positive": (np.array(ending_balances) > 0).mean() * 100,
            "trades_used": profits.tolist(),
        }

        # Result list for display
        result_list = [
            {"label": "Min Ending Balance", "value": results["min"], "is_percent": False, "icon": "bi-currency-dollar", "color": "danger"},
            {"label": "Max Ending Balance", "value": results["max"], "is_percent": False, "icon": "bi-currency-dollar", "color": "success"},
            {"label": "Median Ending Balance", "value": results["median"], "is_percent": False, "icon": "bi-currency-dollar", "color": "info"},
            {"label": "Probability of Profit", "value": results["prob_positive"], "is_percent": True, "icon": "bi-emoji-smile", "color": "primary"},
        ]

        # Generate Equity Curve Plot
        plt.figure(figsize=(12,6))

        for curve in equity_curves:
            plt.plot(curve, alpha=0.3)
        plt.title("Equity Curves")
        plt.xlabel("Trade")
        plt.ylabel("Cumulative Profit")
        plt.tight_layout()
        buffer = BytesIO()
        plt.savefig(buffer, format="png")
        buffer.seek(0)
        equity_curve_base64 = base64.b64encode(buffer.read()).decode("utf-8")
        plt.close()

        # Simulation Summary
        summary = {
            "range_start": start,
            "range_end": end,
            "trade_count": len(profits),
            "date_start": df_range["date"].dropna().min().strftime("%Y-%m-%d %H:%M") if df_range["date"].notna().any() else None,
            "date_end": df_range["date"].dropna().max().strftime("%Y-%m-%d %H:%M") if df_range["date"].notna().any() else None,
        }

        return render(request, "analysis/simulation_run.html", {
            "trade_count": trade_count,
            "results": results,
            "result_list": result_list,
            "equity_curve": equity_curve_base64,
            "form_data": form_data,
            "summary": summary,
        })

    # GET request fallback
    return render(request, "analysis/simulation_run.html")



@login_required
def simulation_scenario_view(request):
    instruction = None
    trade_count = None
    scenarios = []
    form_data = {}  # to hold user inputs

    if request.method == "POST":
        # Reset
        if "reset" in request.POST:
            request.session.pop("uploaded_df", None)
            return render(request, "analysis/simulation_scenario.html", {
                "instruction": "Form reset successfully.",
            })

        # File Upload
        if request.FILES.get("file"):
            file = request.FILES["file"]
            filename = file.name.lower()
            try:
                if filename.endswith(".csv"):
                    df = pd.read_csv(file)
                elif filename.endswith(".xlsx") or filename.endswith(".xls"):
                    df = pd.read_excel(file, engine="openpyxl")
                else:
                    instruction = "Unsupported file format. Please upload a CSV or Excel file."
                    return render(request, "analysis/simulation_scenario.html", {"instruction": instruction})
            except Exception as e:
                instruction = f"Error reading file: {e}"
                return render(request, "analysis/simulation_scenario.html", {"instruction": instruction})

            df.columns = df.columns.str.strip().str.lower()
            if "profit" not in df.columns:
                instruction = "Your file must have a 'profit' column."
                return render(request, "analysis/simulation_scenario.html", {"instruction": instruction})

            if "open" in df.columns:
                df["date"] = pd.to_datetime(df["open"], errors="coerce")
            else:
                df["date"] = pd.NaT

            request.session["uploaded_df"] = df.to_json(date_format="iso")
            trade_count = len(df)

            return render(request, "analysis/simulation_scenario.html", {
                "trade_count": trade_count
            })

        # Load from session
        if "uploaded_df" not in request.session:
            instruction = "Please upload a data file first."
            return render(request, "analysis/simulation_scenario.html", {"instruction": instruction})

        df = pd.read_json(request.session["uploaded_df"])
        trade_count = len(df)

        # Process scenarios
        for i in ["1", "2", "3"]:
            label = f"Scenario {i}"
            n_sim = request.POST.get(f"num_simulations_{i}", "")
            n_trades = request.POST.get(f"num_trades_{i}", "")
            start = request.POST.get(f"range_start_{i}", "")
            end = request.POST.get(f"range_end_{i}", "")
            start_date = request.POST.get(f"start_date_{i}", "")
            end_date = request.POST.get(f"end_date_{i}", "")

            form_data[i] = {
                "num_simulations": n_sim,
                "num_trades": n_trades,
                "range_start": start,
                "range_end": end,
                "start_date": start_date,
                "end_date": end_date,
            }

            try:
                if not n_sim or not n_trades or int(n_sim) <= 0 or int(n_trades) <= 0:
                    scenarios.append({"label": label, "error": "Skipped: No parameters."})
                    continue

                n_sim = int(n_sim)
                n_trades = int(n_trades)
                start = int(start) if start else 0
                end = int(end) if end else len(df)

                df_range = df.iloc[start:end]

                if start_date and end_date:
                    try:
                        sd = pd.to_datetime(start_date)
                        ed = pd.to_datetime(end_date)
                        df_range = df_range[df_range["date"].between(sd, ed)]
                    except Exception:
                        pass

                profits = df_range["profit"].dropna().values
                if len(profits) == 0:
                    scenarios.append({"label": label, "error": "No trades matched filters."})
                    continue

                ending_balances = []
                equity_curves = []
                for _ in range(n_sim):
                    sim = np.random.choice(profits, size=n_trades, replace=True)
                    ending_balances.append(sim.sum())
                    equity_curves.append(np.cumsum(sim))

                plt.figure(figsize=(6, 3))
                for curve in equity_curves:
                    plt.plot(curve, alpha=0.3)
                plt.title(label)
                plt.tight_layout()
                buf = BytesIO()
                plt.savefig(buf, format="png")
                buf.seek(0)
                chart = base64.b64encode(buf.read()).decode("utf-8")
                plt.close()

                scenarios.append({
                    "label": label,
                    "min": float(np.min(ending_balances)),
                    "max": float(np.max(ending_balances)),
                    "median": float(np.median(ending_balances)),
                    "prob_positive": float((np.array(ending_balances) > 0).mean() * 100),
                    "chart": chart
                })

            except Exception as e:
                scenarios.append({"label": label, "error": f"Error: {e}"})

        return render(request, "analysis/simulation_scenario.html", {
            "trade_count": trade_count,
            "scenarios": scenarios,
            "form_data": form_data
        })

    return render(request, "analysis/simulation_scenario.html")




@login_required
def simulation_run_view(request):
    instruction = None
    trade_count = None
    result_list = []
    equity_curve_base64 = None
    date_start = None
    date_end = None

    if request.method == "POST":
        if "reset" in request.POST:
            request.session.pop("uploaded_df", None)
            return render(request, "analysis/simulation_run.html", {"instruction": "Form reset successfully."})

        if request.FILES.get("file"):
            file = request.FILES["file"]
            filename = file.name.lower()
            try:
                if filename.endswith(".csv"):
                    df = pd.read_csv(file)
                elif filename.endswith(".xlsx") or filename.endswith(".xls"):
                    df = pd.read_excel(file, engine="openpyxl")
                else:
                    return render(request, "analysis/simulation_run.html", {
                        "instruction": "Unsupported file format. Please upload a CSV or Excel file."
                    })
            except Exception as e:
                return render(request, "analysis/simulation_run.html", {
                    "instruction": f"Error reading file: {e}"
                })

            df.columns = df.columns.str.strip().str.lower()
            if "profit" not in df.columns:
                return render(request, "analysis/simulation_run.html", {
                    "instruction": "Your file must have a 'profit' column."
                })

            if "open" in df.columns:
                df["date"] = pd.to_datetime(df["open"], errors="coerce")
            else:
                df["date"] = pd.NaT

            request.session["uploaded_df"] = df.to_json(date_format="iso")
            trade_count = len(df)

            if df["date"].notna().any():
                dates = df["date"].dropna()
                date_start = dates.min().strftime("%Y-%m-%d %H:%M")
                date_end = dates.max().strftime("%Y-%m-%d %H:%M")

            return render(request, "analysis/simulation_run.html", {
                "trade_count": trade_count,
                "date_start": date_start,
                "date_end": date_end,
            })

        if "uploaded_df" not in request.session:
            return render(request, "analysis/simulation_run.html", {
                "instruction": "Please upload a data file first."
            })

        df = pd.read_json(request.session["uploaded_df"])
        trade_count = len(df)

        try:
            n_sim = int(request.POST.get("num_simulations"))
            n_trades = int(request.POST.get("num_trades"))
        except Exception:
            return render(request, "analysis/simulation_run.html", {
                "instruction": "Please enter valid numbers for simulations and trades.",
                "trade_count": trade_count,
            })

        start = int(request.POST.get("range_start") or 0)
        end = int(request.POST.get("range_end") or len(df))
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date")

        df_range = df.iloc[start:end]

        if start_date and end_date:
            try:
                sd = pd.to_datetime(start_date)
                ed = pd.to_datetime(end_date)
                df_range = df_range[df_range["date"].between(sd, ed)]
            except Exception:
                pass

        profits = df_range["profit"].dropna().values
        if len(profits) == 0:
            return render(request, "analysis/simulation_run.html", {
                "instruction": "No trades matched your filters.",
                "trade_count": trade_count,
            })

        # Run simulation
        ending_balances = []
        equity_curves = []
        for _ in range(n_sim):
            sim = np.random.choice(profits, size=n_trades, replace=True)
            ending_balances.append(sim.sum())
            equity_curves.append(np.cumsum(sim))

        results_data = {
            "min": float(np.min(ending_balances)),
            "max": float(np.max(ending_balances)),
            "median": float(np.median(ending_balances)),
            "prob_positive": float((np.array(ending_balances) > 0).mean() * 100),
        }

        result_list = [
            {"label": "Min Ending Balance", "value": results_data["min"], "is_percent": False, "icon": "bi-currency-dollar", "color": "danger"},
            {"label": "Max Ending Balance", "value": results_data["max"], "is_percent": False, "icon": "bi-currency-dollar", "color": "success"},
            {"label": "Median Ending Balance", "value": results_data["median"], "is_percent": False, "icon": "bi-currency-dollar", "color": "info"},
            {"label": "Probability of Profit", "value": results_data["prob_positive"], "is_percent": True, "icon": "bi-emoji-smile", "color": "primary"},
        ]

        plt.figure(figsize=(8, 4))
        for curve in equity_curves:
            plt.plot(curve, alpha=0.3)
        plt.title("Equity Curves")
        plt.xlabel("Trade Number")
        plt.ylabel("Cumulative Profit")
        plt.tight_layout()
        buf = BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        equity_curve_base64 = base64.b64encode(buf.read()).decode("utf-8")
        plt.close()

        SimulationHistory.objects.create(
            user=request.user,
            label="Monte Carlo Simulation",
            parameters={
                "num_simulations": n_sim,
                "num_trades": n_trades,
                "range_start": start,
                "range_end": end,
                "start_date": start_date,
                "end_date": end_date,
            },
            results=results_data,
            chart_base64=equity_curve_base64,
        )

        return render(request, "analysis/simulation_run.html", {
            "trade_count": trade_count,
            "result_list": result_list,
            "equity_curve": equity_curve_base64,
        })

    return render(request, "analysis/simulation_run.html")




@login_required
def simulation_history_view(request):
    # Get query parameters
    query = request.GET.get("q", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    page_number = request.GET.get("page")

    # Start with simulations belonging to the current user
    qs = SimulationHistory.objects.filter(user=request.user)

    # Apply search filter
    if query:
        qs = qs.filter(
            Q(label__icontains=query) |
            Q(parameters__icontains=query) |
            Q(results__icontains=query)
        )

    # Apply date filters
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    # Order newest first
    qs = qs.order_by("-created_at")

    # Paginate (6 per page)
    paginator = Paginator(qs, 6)
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "analysis/simulation_history.html",
        {
            "simulations": page_obj,
            "page_obj": page_obj,
            "query": query,
            "date_from": date_from,
            "date_to": date_to,
        }
    )



@login_required
def simulation_delete_view(request, pk):
    sim = get_object_or_404(SimulationHistory, pk=pk, user=request.user)
    if request.method == "POST":
        sim.delete()
        messages.success(request, "Simulation deleted successfully.")
        return redirect("simulation_history")
    return render(request, "analysis/simulation_confirm_delete.html", {"sim": sim})


@login_required
def simulation_download_json_view(request, pk):
    sim = get_object_or_404(SimulationHistory, pk=pk, user=request.user)
    response = HttpResponse(
        json.dumps(sim.results, indent=2),
        content_type="application/json"
    )
    response["Content-Disposition"] = f'attachment; filename="{sim.label}.json"'
    return response


@login_required
def simulation_download_chart_view(request, pk):
    sim = get_object_or_404(SimulationHistory, pk=pk, user=request.user)
    image_data = base64.b64decode(sim.chart_base64)
    response = HttpResponse(image_data, content_type="image/png")
    response["Content-Disposition"] = f'attachment; filename="{sim.label}.png"'
    return response


@login_required
def simulation_detail_view(request, pk):
    sim = get_object_or_404(SimulationHistory, pk=pk, user=request.user)
    return render(request, "analysis/simulation_detail.html", {"sim": sim})

@login_required
def simulation_delete_view(request, pk):
    sim = get_object_or_404(SimulationHistory, pk=pk, user=request.user)
    if request.method == "POST":
        sim.delete()
        return redirect("simulation_history")
    return render(request, "analysis/simulation_confirm_delete.html", {"sim": sim})

