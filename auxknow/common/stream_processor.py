"""
Stream processor module for handling streaming responses from the API.
"""

from typing import Optional, Generator, Any, Callable
from dataclasses import dataclass, field
from .models import AuxKnowAnswer
from ..common.printer import Printer
from ..common.constants import Constants


@dataclass
class StreamBuffer:
    """Container for stream processing state."""

    content: str = Constants.STREAM_DEFAULT_BUFFER_CONTENT
    is_in_think_block: bool = Constants.STREAM_DEFAULT_IS_IN_THINK_BLOCK
    full_answer: str = Constants.STREAM_DEFAULT_FULL_ANSWER
    citations: list[str] = field(default_factory=list)

    def append(self, chunk: str) -> None:
        """Append chunk to buffer content."""
        self.content += chunk

    def clear(self) -> None:
        """Clear buffer content."""
        self.content = Constants.STREAM_DEFAULT_BUFFER_CONTENT


class StreamProcessor:
    """Handles processing of streamed response chunks."""

    THINK_BLOCK_START = Constants.STREAM_BLOCK_START
    THINK_BLOCK_END = Constants.STREAM_BLOCK_END
    THINK_BLOCK_END_LEN = len(THINK_BLOCK_END)

    @staticmethod
    def extract_think_block(
        buffer: StreamBuffer, verbose=Constants.DEFAULT_VERBOSE_ENABLED
    ) -> Optional[str]:
        """Extract and remove think block content from buffer.

        Args:
            buffer: StreamBuffer containing content to process

        Returns:
            Optional[str]: Extracted content outside think block if any
        """
        try:
            if buffer.is_in_think_block:
                end_idx = buffer.content.find(StreamProcessor.THINK_BLOCK_END)
                if end_idx == -1:
                    return None
                content = buffer.content[
                    end_idx + StreamProcessor.THINK_BLOCK_END_LEN :
                ]
                buffer.content = content
                buffer.is_in_think_block = False
                return content

            start_idx = buffer.content.find(StreamProcessor.THINK_BLOCK_START)
            if start_idx == -1:
                if buffer.content:
                    content = buffer.content
                    buffer.clear()
                    return content
                return None

            if start_idx > 0:
                pre_think = buffer.content[:start_idx]
                buffer.content = buffer.content[
                    start_idx + len(StreamProcessor.THINK_BLOCK_START) :
                ]
                buffer.is_in_think_block = True
                return pre_think

            buffer.content = buffer.content[
                start_idx + len(StreamProcessor.THINK_BLOCK_START) :
            ]
            buffer.is_in_think_block = True
            return None
        except Exception as e:
            Printer.verbose_logger(
                verbose,
                Printer.print_red_message,
                Constants.STREAM_PROCESSOR_ERROR_MSG(e),
            )
            return None

    @classmethod
    def process_stream(
        cls,
        response_stream: Generator[Any, None, None],
        citation_extractor: Callable[[Any], list[str]],
        verbose: bool = Constants.DEFAULT_VERBOSE_ENABLED,
    ) -> Generator[AuxKnowAnswer, None, None]:
        """Process response stream and yield answers.

        Args:
            response_stream: Stream of response chunks
            citation_extractor: Function to extract citations from response

        Yields:
            AuxKnowAnswer objects containing processed chunks
        """
        buffer = StreamBuffer()

        for response in response_stream:
            chunk = response.choices[0].delta.content
            if not chunk:
                continue

            buffer.append(chunk)

            while True:
                extracted_content = cls.extract_think_block(buffer, verbose=verbose)
                if extracted_content is None:
                    break

                new_citations = citation_extractor(response)
                if new_citations:
                    buffer.citations.extend(new_citations)
                    buffer.citations = list(set(buffer.citations))

                buffer.full_answer += extracted_content
                yield AuxKnowAnswer(
                    answer=extracted_content,
                    citations=buffer.citations,
                    is_final=False,
                )

        if buffer.content and not buffer.is_in_think_block:
            buffer.full_answer += buffer.content
            yield AuxKnowAnswer(
                answer=buffer.full_answer,
                citations=buffer.citations,
                is_final=True,
            )

        yield AuxKnowAnswer(
            answer=buffer.content,
            citations=buffer.citations,
            is_final=True,
        )
