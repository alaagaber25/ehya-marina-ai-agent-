import base64
import struct


class AudioCodec:
    """
    A Utility class that helps decoding audio data from base64 pcm and encoding it to base64 wave
    """

    @classmethod
    def to_wav(cls, pcm_data: str) -> str:
        return base64.b64encode(
            cls.pcm_to_wav_bytes(base64.b64decode(pcm_data))
        ).decode("utf-8")

    @classmethod
    def to_pcm(cls, wav_data: str) -> str:
        # return base64.b64encode(
        #     cls.wav_to_pcm_bytes(base64.b64decode(wav_data))
        # ).decode("utf-8")
        raise NotImplementedError

    @staticmethod
    def pcm_to_wav_bytes(
        pcm: bytes, sample_rate: int = 24000, channels: int = 1, sampwidth: int = 2
    ) -> bytes:
        """
        Example usage:

        raw_pcm = b"\\x00\\x00\\xff\\xff" * 1000  # 1000 fake 16-bit samples
        wav_bytes = pcm_to_wav_bytes(raw_pcm, 24000, 1, 2)

        ---
        pcm: raw little-endian PCM samples
        returns: raw bytes of a complete RIFF/WAVE file
        """
        data_size = len(pcm)
        riff_size = data_size + 36  # 4 + (8 + 16) + (8 + data_size)

        header = (
            b"RIFF"
            + struct.pack("<I", riff_size)
            + b"WAVE"
            + b"fmt "
            + struct.pack(
                "<IHHIIHH",
                16,  # subchunk size
                1,  # PCM format
                channels,
                sample_rate,
                sample_rate * channels * sampwidth,
                channels * sampwidth,
                sampwidth * 8,
            )
            + b"data"
            + struct.pack("<I", data_size)
        )
        return header + pcm
