<!-- PROJECT LOGO -->

<div align="center">
  <h1 align="center">Account Abstraction paymaster- ERC-4337</h1>
</div>
<br/><br/>

# About

SafeHodl Wallet is a smart contract wallet for Ethereum Mainnet and EVM compatible rollups.<br/>
This repo includes the paymaster RPC service.

# Features
- a paymaster RPC that approves and signs operation to allow for gas sponsorship and paying gas with ERC-20 tokens.
- admin control panel to view processed operations

# How to use this repo

### Setup env
```
cd paymaster
mv .env.example .env
cd ../
```

### Generate DJANGO secret key
```
python3 -c 'import random; result = "".join([random.choice("abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)") for i in range(50)]); print(result)'
```

### Create a virtual environment
```
python3 -m venv .venv
```

### Run virtual environment (linux)
```
source .venv/bin/activate
```

### Install required libs
```
pip install wheel
pip install -r requirements.txt
```

### Setup the database
```
python manage.py makemigrations paymaster
python manage.py migrate
python manage.py loaddata paymaster/tokenSeed.json
```

### Change .env variables if needed 
the defaults work with the <a href='https://github.com/victor-tucci/safehodl-contract'>SafeHodlContracts</a> repo for testing


### Create Super user for admin panel
```
python manage.py createsuperuser
```

### Run the server with default os.environ
```
python manage.py runserver
```

### Run the server with a custom os.environ
```
python3 manage.py runserver --port 1337 --chainId 10 --HTTPProvider http://localhost:8545
```

### Access the control panel
```
http://127.0.0.1:8000/admin/
```

## Using Docker:
```
docker compose up -d
```

## TODO
- [ ] Gas limit calculation and verification (paymaster)
- [ ] Fetching live token prices and verifying source wallets balance (paymaster)
- [ ] Adding white list and black list for source wallets (paymaster)


<!-- LICENSE -->
## License

MIT

<!-- ACKNOWLEDGMENTS -->
## Acknowledgments
* <a href='https://github.com/eth-infinitism/account-abstraction'>eth-infinitism/account-abstraction</a>
* <a href='https://github.com/safe-global/safe-eth-py'>Gnosis-py</a>
* <a href='https://eips.ethereum.org/EIPS/eip-4337'>EIP-4337: Account Abstraction via Entry Point Contract specification </a>
