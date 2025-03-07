import math

from .models import ERC20ApprovedToken
from .serializers import OperationSerialzer
from jsonrpcserver import method, Result, Success, dispatch, Error
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse

import environ
import requests
from web3 import Web3
from web3.middleware import geth_poa_middleware
from hexbytes import HexBytes
import re
from eth_account.messages import encode_defunct
from eth_abi import decode

env = environ.Env()

SUPPORTED_CHAINS = {"11155111": {'address': env('SEPOLIA_PM'), 'provider': env('SEPOLIA_PROVIDER')},
                    "80002": {'address': env('AMOY_PM'), 'provider': env('AMOY_PROVIDER')}}
# Todo: check wallet balance if it has the required tokens to pay for the paymaster fees
# Todo: accept the full bundle as an input and check the approve operation
@method
def pm_sponsorUserOperation(request, token_address, chainId) -> Result:
    abi = [{"inputs":[{"components":[{"internalType":"address","name":"sender","type":"address"},{"internalType":"uint256","name":"nonce","type":"uint256"},{"internalType":"bytes","name":"initCode","type":"bytes"},{"internalType":"bytes","name":"callData","type":"bytes"},{"internalType":"uint256","name":"callGasLimit","type":"uint256"},{"internalType":"uint256","name":"verificationGasLimit","type":"uint256"},{"internalType":"uint256","name":"preVerificationGas","type":"uint256"},{"internalType":"uint256","name":"maxFeePerGas","type":"uint256"},{"internalType":"uint256","name":"maxPriorityFeePerGas","type":"uint256"},{"internalType":"bytes","name":"paymasterAndData","type":"bytes"},{"internalType":"bytes","name":"signature","type":"bytes"}],"internalType":"struct UserOperation","name":"userOp","type":"tuple"},{"components":[{"internalType":"contract IERC20Metadata","name":"token","type":"address"},{"internalType":"enum SafeHodlPaymaster.SponsoringMode","name":"mode","type":"uint8"},{"internalType":"uint48","name":"validUntil","type":"uint48"},{"internalType":"uint256","name":"fee","type":"uint256"},{"internalType":"uint256","name":"exchangeRate","type":"uint256"},{"internalType":"bytes","name":"signature","type":"bytes"}],"internalType":"struct SafeHodlPaymaster.PaymasterData","name":"paymasterData","type":"tuple"}],"name":"getHash","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"}]
    ERC20_ABI = [{"inputs": [{"name": "_owner","type": "address"}],"name": "balanceOf","outputs": [{"name": "balance","type": "uint256"}],"stateMutability": "view","type": "function"},]

    if chainId not in SUPPORTED_CHAINS:
        return Error(2, "Unsupported ChainID", data=f"Supported chains are: {', '.join(SUPPORTED_CHAINS)}")

    http_provider = SUPPORTED_CHAINS[chainId].get('provider')
    if not http_provider:
        return Error(2, "HTTP Provider not configured for the ChainID", data="")
    
    w3 = Web3(Web3.HTTPProvider(http_provider))

    if chainId not in SUPPORTED_CHAINS:
        return Error(2, "Unsupported ChainID", data=f"Supported chains are: {', '.join(SUPPORTED_CHAINS)}")    
    
    paymaster_address = SUPPORTED_CHAINS[chainId].get('address')

    if not paymaster_address:
        return Error(2, " paymaster address not configured for the ChainID", data="")

    paymaster = w3.eth.contract(address=paymaster_address, abi=abi)
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    # Verify connection
    if w3.is_connected():
        print('\033[96m' +"Connected to the network!" + '\033[39m')
    else:
        return Error(1, "connection Failed", data="")
    
    print('\033[96m' + "Paymaster Operation received." + '\033[39m')
    token_object = ERC20ApprovedToken.objects.filter(chains__has_key=chainId).filter(chains__icontains=token_address)
    if len(token_object) < 1:
        return Error(2, "Unsupported token", data="")

    token = token_object.first().chains[chainId]
    if not token["enabled"]:
        return Error(2, "Unsupported token", data="")

    serialzer = OperationSerialzer(data=request)

    if not serialzer.is_valid():
        return Error(400, "BAD REQUEST")

    print('\033[96m' + "Serialize is done." + '\033[39m')
    op = (
        serialzer.data["sender"],
        int(serialzer.data["nonce"], 16),
        HexBytes(serialzer.data["initCode"]),
        HexBytes(serialzer.data["callData"]),
        int(serialzer.data["callGasLimit"], 16),
        int(serialzer.data["verificationGasLimit"], 16),
        int(serialzer.data["preVerificationGas"], 16),
        int(serialzer.data["maxFeePerGas"], 16),
        int(serialzer.data["maxPriorityFeePerGas"], 16),
        HexBytes(serialzer.data["paymasterAndData"]),
        HexBytes(serialzer.data["signature"]),
    )

    additional_gas = 35000
    exchange_rate = _get_token_rate(token)
    print('\033[96m' + "Exchange rate received." + '\033[39m')

    # Accessing tuple elements by index
    sender = op[0]
    call_data = op[3]
    callGasLimit = op[4]
    verificationGasLimit = op[5]
    preVerificationGas = op[6]
    maxFeePerGas = op[7]

    # Calculate total gas
    total_gas = preVerificationGas + verificationGasLimit + callGasLimit
    erc20_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
    wallet_balance = erc20_contract.functions.balanceOf(sender).call()
    _dest, _value, _func, _approveToken, _approveFunc = decode(["address", "uint256", "bytes", "address", "bytes"], call_data[4:])
    # Calculate actual token cost
    actual_token_cost = ((total_gas * maxFeePerGas + (additional_gas * maxFeePerGas)) * exchange_rate) // 10**18
    if (_func and (_dest.lower() == _approveToken.lower())) :
        To,Amount = decode(["address", "uint256"], _func[4:])
        if((Amount + actual_token_cost) > wallet_balance):
            return Error(101, "Insufficient token to complete the transaction", data="")
    elif wallet_balance < actual_token_cost:
        return Error(3, "Insufficient token", data="")


    paymasterData = [
        token["address"],
        1,  # SponsoringMode (GAS ONLY)
        w3.eth.get_block("latest").timestamp + 180,  # validUntil 3 minutes in the future
        0,  # Fee (in case mode == 0)
        exchange_rate,  # Exchange Rate
        b'',
    ]

    hash = paymaster.functions.getHash(op, paymasterData).call()
    hash = encode_defunct(hash)
    paymasterSigner = w3.eth.account.from_key(env('paymaster_pk'))
    sig = paymasterSigner.sign_message(hash)
    paymasterData[-1] = HexBytes(sig.signature.hex())

    print('\033[96m' + "Paymaster signature signed." + '\033[39m')
    paymasterAndData = (
          str(paymasterData[0][2:])
        + str("{0:0{1}x}".format(paymasterData[1], 2))
        + str("{0:0{1}x}".format(paymasterData[2], 12))
        + str("{0:0{1}x}".format(paymasterData[3], 64))
        + str("{0:0{1}x}".format(paymasterData[4], 64))
        + sig.signature.hex()
    )

    return Success(paymasterAndData)

@method
def pm_getApprovedTokens(chainId) -> Result:
    result = []

    if chainId not in SUPPORTED_CHAINS:
        return Error(2, "Unsupported ChainID", data=f"Supported chains are: {', '.join(SUPPORTED_CHAINS)}")

    approved_tokens = ERC20ApprovedToken.objects.filter(chains__has_key=chainId)
    print('approved_tokens',approved_tokens)
    paymaster_address = SUPPORTED_CHAINS[chainId].get('address')
    if not paymaster_address:
        return Error(2, " paymaster address not configured for the ChainID", data="")

    for approvedToken in approved_tokens:
        token = approvedToken.chains[chainId]
        exchange_rate = _get_token_rate(token)
        result.append({
            "address": token["address"],
            "paymaster": paymaster_address,
            "exchangeRate": exchange_rate
        })
    return Success(result)

@method
def pm_chainId() -> Result:
    result = env('chainId')
    return Success(result)

@method
def pm_supportedEntryPoints() -> Result:
    result = str(env('entryPoint_add'))
    return Success(result)

def _get_token_rate(token):
    rate_request = requests.get(token["exchangeRateSource"])
    rate_float = 1 / float(re.search(r'"eth":([\d.eE-]+)', rate_request.content.decode()).group(1))
    rate = math.ceil(rate_float * (10 ** token["decimals"]))
    return rate


@csrf_exempt
def jsonrpc(request):
    return HttpResponse(
        dispatch(request.body.decode()), content_type="application/json"
    )

@method
def get_supported_tokens():
    tokens = ERC20ApprovedToken.objects.all()
    supported_tokens = []

    for token in tokens:
        supported_tokens.append({
            "name": token.name,
            "chains": token.chains  # This should be a dict containing chain details
        })

    return Success(supported_tokens)