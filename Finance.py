import pandas as pd
import matplotlib.pyplot as plt


DATA_FILE = "data.csv"


def load_data():
    try:
        return pd.read_csv(DATA_FILE)
    except FileNotFoundError:
        return pd.DataFrame(columns=["Date", "Description", "Amount", "Type"])


def save_data(df):
    df.to_csv(DATA_FILE, index=False)


def add_transaction(date, description, amount, transaction_type):
    df = load_data()
    new_row = pd.DataFrame(
        [{
            "Date": date,
            "Description": description,
            "Amount": amount,
            "Type": transaction_type
        }]
    )
    df = pd.concat([df, new_row], ignore_index=True)
    save_data(df)


def show_summary():
    df = load_data()

    if df.empty:
        print("No transactions recorded yet.")
        return

    income = df[df["Type"] == "Income"]["Amount"].sum()
    expenses = df[df["Type"] == "Expense"]["Amount"].sum()
    net_savings = income - expenses

    print(f"Total Income: ${income:.2f}")
    print(f"Total Expenses: ${expenses:.2f}")
    print(f"Net Savings: ${net_savings:.2f}")


def show_transactions():
    df = load_data()

    if df.empty:
        print("No transactions recorded yet.")
        return

    print("\n--- Transactions ---")
    print(df.to_string(index=False))


def visualize_data():
    df = load_data()

    if df.empty:
        print("No transactions available to visualize.")
        return

    summary = df.groupby("Type")["Amount"].sum()

    plt.figure(figsize=(6, 4))
    summary.plot(kind="bar", color=["green", "red"])
    plt.title("Income vs Expenses")
    plt.xlabel("Type")
    plt.ylabel("Amount ($)")
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.show()


def get_transaction_type():
    while True:
        transaction_type = input("Enter type (Income/Expense): ").strip().title()
        if transaction_type in ["Income", "Expense"]:
            return transaction_type
        print("Invalid type. Please enter Income or Expense.")


def main():
    while True:
        print("\n--- Personal Finance Tracker ---")
        print("1. Add Transaction")
        print("2. Show Summary")
        print("3. View Transactions")
        print("4. Visualize Data")
        print("5. Exit")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            date = input("Enter date (YYYY-MM-DD): ").strip()
            description = input("Enter description: ").strip()

            try:
                amount = float(input("Enter amount: ").strip())
            except ValueError:
                print("Invalid amount. Please enter a numeric value.")
                continue

            transaction_type = get_transaction_type()
            add_transaction(date, description, amount, transaction_type)
            print("Transaction added successfully.")

        elif choice == "2":
            show_summary()

        elif choice == "3":
            show_transactions()

        elif choice == "4":
            visualize_data()

        elif choice == "5":
            print("Exiting the program.")
            break

        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main()
