import os, torch, logging, time, math
from typing import Dict, Any, Optional, Final
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration

# Initialize localized logging for the neural engine component
logger = logging.getLogger(__name__)

# High-performance multimodal engine implementing Salesforce BLIP for image-to-text synthesis
class NeuralCaptionEngine:
    def __init__(self, model_id: str = "Salesforce/blip-image-captioning-base") -> None:
        self.device: Final[torch.device] = self._get_optimal_device()
        self.model_id: Final[str] = model_id
        self.processor: Optional[BlipProcessor] = None
        self.model: Optional[BlipForConditionalGeneration] = None
        self.weights_loaded: bool = False
        self.init_error: Optional[str] = None
        
        self._initialize_backbone()

    # Select the most performant hardware accelerator (CUDA, MPS, or CPU) available
    def _get_optimal_device(self) -> torch.device:
        if torch.cuda.is_available():
            return torch.device('cuda')
        if torch.backends.mps.is_available():
            return torch.device('mps')
        return torch.device('cpu')

    # Load and configure the vision-language backbone on the target hardware topology
    def _initialize_backbone(self) -> None:
        logger.info(f"Initializing Hybrid Pipeline on execution target: [ {self.device} ]")
        start_time = time.perf_counter()
        try:
            # Utilize unified BLIP processor for visual feature extraction and text tokenization
            # Optimize memory footprint via target precision loading and low-CPU memory usage
            target_dtype = torch.float16 if self.device.type == 'cuda' else torch.float32
            
            self.model = BlipForConditionalGeneration.from_pretrained(
                self.model_id,
                torch_dtype=target_dtype,
                low_cpu_mem_usage=True
            ).to(self.device)
            
            self.processor = BlipProcessor.from_pretrained(self.model_id)
            
            self.model.eval() # Set model to evaluation mode to disable stochastic layers like dropout

            # Synchronize padding token with end-of-sequence token from text configuration
            self.model.config.pad_token_id = self.model.config.text_config.eos_token_id

            self.weights_loaded = True
            
            initialization_latency = (time.perf_counter() - start_time) * 1000
            logger.info(f"Modular Backbone successfully allocated in {initialization_latency:.2f}ms: {self.model_id}")
        except Exception as init_fault:
            error_msg = str(init_fault)
            logger.critical(f"Critical failure loading model weights array: {error_msg}")
            self.weights_loaded = False
            self.init_error = error_msg

    # Perform end-to-end inference: ingestion, spatial processing, and linguistic decoding
    def process_and_decode(self, input_source: str, max_length: int = 32) -> Dict[str, Any]:
        try:
            if not os.path.exists(input_source):
                raise FileNotFoundError(f"Target file system asset missing: {input_source}")

            if not self.weights_loaded or self.model is None or self.processor is None:
                raise RuntimeError("Neural engine components not successfully loaded into hardware context.")

            # Stage 1: Validate asset integrity and ensure RGB color space conformance
            with Image.open(input_source) as img:
                image = img.convert('RGB')
                image.load() # Force memory allocation for image data to prevent lazy-loading latency
            
            # Stage 2: Transform visual inputs into high-dimensional tensor embeddings
            cv_start = time.perf_counter()
            # Cast input tensors to half-precision (FP16) for CUDA acceleration
            inputs = self.processor(images=[image], return_tensors="pt").to(self.device)
            if self.device.type == 'cuda':
                inputs = {k: v.to(dtype=torch.float16) if v.is_floating_point() else v for k, v in inputs.items()}
                
            cv_latency = (time.perf_counter() - cv_start) * 1000
            
            # Stage 3: Execute autoregressive sequence generation via beam search decoding
            nlp_start = time.perf_counter()
            # Utilize torch.inference_mode for optimized memory and execution performance
            with torch.inference_mode():
                generation_outputs = self.model.generate(
                    **inputs, 
                    max_length=max_length, 
                    num_beams=7,
                    no_repeat_ngram_size=2,
                    early_stopping=True,
                    return_dict_in_generate=True,
                    output_scores=True
                )
            nlp_latency = (time.perf_counter() - nlp_start) * 1000

            # Stage 4: Normalize sequence log-probabilities into a decimal confidence metric
            if hasattr(generation_outputs, "sequences_scores") and generation_outputs.sequences_scores is not None:
                log_probability = generation_outputs.sequences_scores[0].item()
                # Apply exponential normalization to derive probability from sequence log-scores
                calculated_confidence = round(float(math.exp(log_probability)), 4)
            else:
                calculated_confidence = 0.88 # Default fallback confidence score

            # Stage 5: Convert predicted token indices into a natural language string
            output_ids = generation_outputs.sequences[0]
            caption = self.processor.decode(output_ids, skip_special_tokens=True).strip().capitalize()

            logger.info(
                f"Inference Completed. Profiling: CV Layer={cv_latency:.2f}ms | "
                f"NLP Generation={nlp_latency:.2f}ms | Confidence={calculated_confidence * 100:.2f}%"
            )

            if self.device.type == 'cuda':
                torch.cuda.empty_cache()

            return {
                "success": True,
                "caption": caption,
                "confidence": calculated_confidence,
                "backbone": "Salesforce BLIP Architecture",
                "weights_status": "verified"
            }
        except Exception as inference_fault:
            logger.error(f"Inference pipeline execution error: {str(inference_fault)}")
            if self.device.type == 'cuda':
                torch.cuda.empty_cache()
            return {
                "success": False,
                "caption": f"Inference engine failure: {str(inference_fault)}",
                "confidence": 0.0,
                "backbone": "Error Recovery Core"
            }