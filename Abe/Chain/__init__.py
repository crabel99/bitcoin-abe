# Copyright(C) 2014 by Abe developers.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License along with this program.  If not, see
# <http://www.gnu.org/licenses/agpl.html>.
"""Chains to be used"""

from typing import Tuple, Union
from .. import deserialize, util
from ..deserialize import opcodes, Transaction, Block, TxIn, TxOut
from ..typing import ScriptMultisig
from ..streams import BCDataStream

# pylint: disable=invalid-name
PUBKEY_HASH_LENGTH = 20
MAX_MULTISIG_KEYS = 3

# Template to match a pubkey hash ("Bitcoin address transaction") in
# txout_scriptPubKey.  OP_PUSHDATA4 matches any data push.
SCRIPT_ADDRESS_TEMPLATE = [
    opcodes.OP_DUP,
    opcodes.OP_HASH160,
    opcodes.OP_PUSHDATA4,
    opcodes.OP_EQUALVERIFY,
    opcodes.OP_CHECKSIG,
]

# Template to match a pubkey ("IP address transaction") in txout_scriptPubKey.
SCRIPT_PUBKEY_TEMPLATE = [opcodes.OP_PUSHDATA4, opcodes.OP_CHECKSIG]

# Template to match a BIP16 pay-to-script-hash (P2SH) output script.
SCRIPT_P2SH_TEMPLATE = [opcodes.OP_HASH160, PUBKEY_HASH_LENGTH, opcodes.OP_EQUAL]

# Template to match a script that can never be redeemed, used in Namecoin.
SCRIPT_BURN_TEMPLATE = [opcodes.OP_RETURN]

SCRIPT_TYPE_INVALID = 0
SCRIPT_TYPE_UNKNOWN = 1
SCRIPT_TYPE_PUBKEY = 2
SCRIPT_TYPE_ADDRESS = 3
SCRIPT_TYPE_BURN = 4
SCRIPT_TYPE_MULTISIG = 5
SCRIPT_TYPE_P2SH = 6


class BaseChain:
    """The basic coin data structure"""

    POLICY_ATTRS = [
        "magic",
        "name",
        "code3",
        "address_version",
        "decimals",
        "script_addr_vers",
    ]
    __all__ = ["id", "policy"] + POLICY_ATTRS

    def __init__(self, src=None, **kwargs):
        for attr in self.__all__:
            if attr in kwargs:
                val = kwargs.get(attr)
            elif hasattr(self, attr):
                continue
            elif src is not None:
                val = getattr(src, attr)
            else:
                val = None
            setattr(self, attr, val)
        self.id: int
        self.name: str
        self.code3: str
        self.address_version: bytes
        self.script_addr_vers: bytes
        self.magic: bytes
        self.decimals: int

    def has_feature(self, feature):  # pylint: disable=unused-argument
        return False

    def ds_parse_block_header(self, data_stream: BCDataStream) -> Block:
        return deserialize.parse_BlockHeader(data_stream)  # type: ignore

    def ds_parse_transaction(self, data_stream: BCDataStream) -> Transaction:
        return deserialize.parse_Transaction(data_stream)  # type: ignore

    def ds_parse_block(self, data_stream: BCDataStream) -> Block:
        block: Block = self.ds_parse_block_header(data_stream)
        block["transactions"] = []
        nTransactions: int = data_stream.read_compact_size()
        # print(nTransactions)
        for _ in range(nTransactions):
            block["transactions"].append(self.ds_parse_transaction(data_stream))
        return block

    def ds_serialize_block(self, data_stream: BCDataStream, block: Block) -> None:
        self.ds_serialize_block_header(data_stream, block)
        data_stream.write_compact_size(len(block["transactions"]))
        for tx in block["transactions"]:
            self.ds_serialize_transaction(data_stream, tx)

    def ds_serialize_block_header(
        self, data_stream: BCDataStream, block: Block
    ) -> None:
        data_stream.write_int32(block["version"])
        data_stream.write(block["hashPrev"])
        data_stream.write(block["hashMerkleRoot"])
        data_stream.write_uint32(block["nTime"])
        data_stream.write_uint32(block["nBits"])
        data_stream.write_uint32(block["nNonce"])

    def ds_serialize_transaction(
        self, data_stream: BCDataStream, tx: Transaction
    ) -> None:
        data_stream.write_int32(tx["version"])
        data_stream.write_compact_size(len(tx["txIn"]))
        for txin in tx["txIn"]:
            self.ds_serialize_txin(data_stream, txin)
        data_stream.write_compact_size(len(tx["txOut"]))
        for txout in tx["txOut"]:
            self.ds_serialize_txout(data_stream, txout)
        data_stream.write_uint32(tx["lockTime"])

    def ds_serialize_txin(self, data_stream: BCDataStream, txin: TxIn) -> None:
        data_stream.write(txin["prevout_hash"])
        data_stream.write_uint32(txin["prevout_n"])
        data_stream.write_string(txin["scriptSig"])
        data_stream.write_uint32(txin["sequence"])

    def ds_serialize_txout(self, data_stream: BCDataStream, txout: TxOut) -> None:
        data_stream.write_int64(txout["value"])
        data_stream.write_string(txout["scriptPubKey"])

    def serialize_block(self, block: Block) -> Union[bytearray, memoryview, None]:
        data_stream = BCDataStream()
        self.ds_serialize_block(data_stream, block)
        return data_stream.input

    def serialize_block_header(
        self, block: Block
    ) -> Union[bytearray, memoryview, None]:
        data_stream = BCDataStream()
        self.ds_serialize_block_header(data_stream, block)
        return data_stream.input

    def serialize_transaction(
        self, tx: Transaction
    ) -> Union[bytearray, memoryview, None]:
        data_stream = BCDataStream()
        self.ds_serialize_transaction(data_stream, tx)
        return data_stream.input

    def ds_block_header_hash(self, data_stream: BCDataStream) -> bytes:
        """For a datastream return the hash of the block header"""
        if isinstance(data_stream.input, (bytearray, memoryview)):
            return util.block_header_hash(
                data_stream.input[
                    data_stream.read_cursor : data_stream.read_cursor + 80
                ]
            )
        return bytes()

    def parse_block_header(self, header: str) -> Block:
        return self.ds_parse_block_header(str_to_ds(header))

    def parse_transaction(self, binary_tx: str) -> Transaction:
        return self.ds_parse_transaction(str_to_ds(binary_tx))

    def is_coinbase_tx(self, tx: dict) -> bool:
        return (
            len(tx["txIn"]) == 1
            and tx["txIn"][0]["prevout_hash"] == self.coinbase_prevout_hash
        )

    coinbase_prevout_hash = util.NULL_HASH
    coinbase_prevout_n = 0xFFFFFFFF
    genesis_hash_prev = util.GENESIS_HASH_PREV

    def parse_txout_script(self, script):
        """
        Return TYPE, DATA where the format of DATA depends on TYPE.

        * SCRIPT_TYPE_INVALID  - DATA is the raw script
        * SCRIPT_TYPE_UNKNOWN  - DATA is the decoded script
        * SCRIPT_TYPE_PUBKEY   - DATA is the binary public key
        * SCRIPT_TYPE_ADDRESS  - DATA is the binary public key hash
        * SCRIPT_TYPE_BURN     - DATA is None
        * SCRIPT_TYPE_MULTISIG - DATA is {"m":M, "pubkeys":list_of_pubkeys}
        * SCRIPT_TYPE_P2SH     - DATA is the binary script hash
        """
        if script is None:
            raise ValueError()
        try:
            decoded = list(deserialize.script_GetOp(script))
        except Exception:
            return SCRIPT_TYPE_INVALID, script
        return self.parse_decoded_txout_script(decoded)

    def parse_decoded_txout_script(
        self, decoded
    ) -> Tuple[int, Union[bytes, ScriptMultisig, None]]:
        if deserialize.match_decoded(decoded, SCRIPT_ADDRESS_TEMPLATE):
            pubkey_hash = decoded[2][1]
            if len(pubkey_hash) == PUBKEY_HASH_LENGTH:
                return SCRIPT_TYPE_ADDRESS, pubkey_hash

        elif deserialize.match_decoded(decoded, SCRIPT_PUBKEY_TEMPLATE):
            pubkey = decoded[0][1]
            return SCRIPT_TYPE_PUBKEY, pubkey

        elif deserialize.match_decoded(decoded, SCRIPT_P2SH_TEMPLATE):
            script_hash = decoded[1][1]
            assert len(script_hash) == PUBKEY_HASH_LENGTH
            return SCRIPT_TYPE_P2SH, script_hash

        elif deserialize.match_decoded(decoded, SCRIPT_BURN_TEMPLATE):
            return SCRIPT_TYPE_BURN, None

        elif len(decoded) >= 4 and decoded[-1][0] == opcodes.OP_CHECKMULTISIG:
            # cf. bitcoin/src/script.cpp:Solver
            n_sig = decoded[-2][0] + 1 - opcodes.OP_1
            m_sig = decoded[0][0] + 1 - opcodes.OP_1
            if (
                1 <= m_sig <= n_sig <= MAX_MULTISIG_KEYS
                and len(decoded) == 3 + n_sig
                and all(
                    [decoded[i][0] <= opcodes.OP_PUSHDATA4 for i in range(1, 1 + n_sig)]
                )
            ):
                return SCRIPT_TYPE_MULTISIG, {
                    "m": m_sig,
                    "pubkeys": [decoded[i][1] for i in range(1, 1 + n_sig)],
                }

        # Namecoin overrides this to accept name operations.
        return SCRIPT_TYPE_UNKNOWN, decoded

    datadir_conf_file_name = "bitcoin.conf"
    datadir_rpcport = 8332


def create(policy, **kwargs) -> BaseChain:
    """Create the database class for testing"""
    mod = __import__(__name__ + "." + policy, fromlist=[policy])
    cls = getattr(mod, policy)
    return cls(policy=policy, **kwargs)  # type:ignore


def str_to_ds(data: str) -> BCDataStream:
    data_stream = BCDataStream()
    data_stream.write(util.hex2b(data))
    return data_stream
