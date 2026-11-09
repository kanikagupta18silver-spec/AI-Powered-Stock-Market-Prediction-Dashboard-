import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
import numpy as np

# Download stock data
stock = yf.download("AAPL", start="2020-01-01", end="2025-01-01")

# Show first 5 rows
print("\nFirst 5 Rows:")
print(stock.head())

# Dataset information
print("\nDataset Info:")
print(stock.info())

# Check missing values
print("\nMissing Values:")
print(stock.isnull().sum())

# Show closing prices
print("\nClosing Prices:")
print(stock['Close'].head())

# Create future prediction column
future_days = 30

stock['Prediction'] = stock[['Close']].shift(-future_days)

# Show prediction dataset
print("\nClose and Prediction Columns:")
print(stock[['Close', 'Prediction']].head())

# Show last rows
print("\nLast Rows:")
print(stock.tail())

# Remove missing values
stock = stock.dropna()

# Final dataset shape
print("\nFinal Dataset Shape:")
print(stock.shape)

# Features (Input)
X = np.array(stock[['Close']])

# Labels (Output)
y = np.array(stock['Prediction'])

# Shape check
print("\nX Shape:")
print(X.shape)

print("\ny Shape:")
print(y.shape)

# Train-test split
X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)

# Create Linear Regression model
model = LinearRegression()

# Train model
model.fit(X_train, y_train)

# Generate predictions
predictions = model.predict(X_test)

# Show first 10 predictions
print("\nFirst 10 Predictions:")
print(predictions[:10])

# Model accuracy
accuracy = model.score(X_test, y_test)

print("\nModel Accuracy:")
print(accuracy)

# Compare actual vs predicted
print("\nActual vs Predicted Values:")

for i in range(5):
    print(
        "Actual:", y_test[i],
        "| Predicted:", predictions[i]
    )

# Plot actual stock closing price
plt.figure(figsize=(12,6))

stock['Close'].plot()

plt.title("Apple Stock Closing Price")
plt.xlabel("Date")
plt.ylabel("Price")

plt.savefig("images/stock_price.png")
plt.show()

# Plot actual vs predicted prices
plt.figure(figsize=(12,6))

plt.plot(y_test[:100], label='Actual Prices')
plt.plot(predictions[:100], label='Predicted Prices')

plt.title("Actual vs Predicted Stock Prices")
plt.xlabel("Data Points")
plt.ylabel("Stock Price")

plt.legend()

plt.savefig("images/prediction_graph.png")
plt.show()

